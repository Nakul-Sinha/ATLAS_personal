import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/status.dart' as ws_status;
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/atlas_event.dart';

/// High level lifecycle of the ATLAS backend socket.
///
/// Named [AtlasConnectionState] rather than ConnectionState to avoid clashing
/// with the ConnectionState enum that Flutter exports from material.dart.
enum AtlasConnectionState { disconnected, connecting, connected, error }

/// Talks to the ATLAS FastAPI backend: a REST health probe plus a bidirectional
/// WebSocket command and progress stream.
///
/// Extends [ChangeNotifier] so widgets can rebuild via ListenableBuilder or
/// AnimatedBuilder whenever the connection state or event list changes.
class AtlasService extends ChangeNotifier {
  AtlasService({this.host = '', this.port = 8000, this.token = ''});

  /// Backend host, for example "192.168.1.20". No scheme and no port here.
  String host;

  /// Backend port. Defaults to the ATLAS backend default of 8000.
  int port;

  /// Optional access token for backends that require auth. An empty string
  /// means the backend is open (no auth) and nothing extra is sent. When set,
  /// it is delivered as the very first frame after the socket opens.
  String token;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;

  AtlasConnectionState _connectionState = AtlasConnectionState.disconnected;
  final List<AtlasEvent> _events = <AtlasEvent>[];
  String? _lastError;

  static const int _maxEvents = 200;

  // ---- Public read only state -------------------------------------------

  AtlasConnectionState get connectionState => _connectionState;

  bool get isConnected => _connectionState == AtlasConnectionState.connected;

  /// Immutable snapshot of the received events, oldest first.
  List<AtlasEvent> get events => List<AtlasEvent>.unmodifiable(_events);

  /// The most recently received event, or null if none has arrived yet.
  AtlasEvent? get latestEvent => _events.isEmpty ? null : _events.last;

  /// The last error observed on the socket or the health check.
  String? get lastError => _lastError;

  String get httpBase => 'http://$host:$port';

  String get wsUrl => 'ws://$host:$port/ws';

  // ---- Configuration -----------------------------------------------------

  /// Updates the target host, port, and optional auth token. Does not open or
  /// close the socket. Pass an empty [token] (the default) for an open backend.
  void configure(String host, int port, {String token = ''}) {
    this.host = host.trim();
    this.port = port;
    this.token = token.trim();
  }

  // ---- Health probe ------------------------------------------------------

  /// Performs an HTTP GET on /health with a short timeout. Returns true when
  /// the server responds 200 and, if the body carries a status field, that
  /// status is "ok". Never throws.
  Future<bool> checkHealth({
    Duration timeout = const Duration(seconds: 4),
  }) async {
    if (host.isEmpty) {
      _lastError = 'No host configured';
      return false;
    }
    try {
      final uri = Uri.parse('$httpBase/health');
      final response = await http.get(uri).timeout(timeout);
      if (response.statusCode != 200) {
        _lastError = 'Health check returned HTTP ${response.statusCode}';
        return false;
      }
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) {
          final status = decoded['status'];
          final healthy = status == null || status == 'ok';
          if (!healthy) {
            _lastError = 'Server reported status "$status"';
          }
          return healthy;
        }
        // 200 with a non object body: treat the server as reachable.
        return true;
      } catch (_) {
        // 200 with a non JSON body: still reachable.
        return true;
      }
    } on TimeoutException {
      _lastError = 'Connection timed out';
      return false;
    } catch (e) {
      _lastError = e.toString();
      return false;
    }
  }

  // ---- WebSocket lifecycle ----------------------------------------------

  /// Opens the WebSocket to /ws and begins listening. Any existing connection
  /// is torn down first, so this is safe to call repeatedly.
  void connect() {
    if (host.isEmpty) {
      _lastError = 'No host configured';
      _setState(AtlasConnectionState.error);
      return;
    }
    _teardown();
    _lastError = null;
    _setState(AtlasConnectionState.connecting);
    try {
      final channel = WebSocketChannel.connect(Uri.parse(wsUrl));
      _channel = channel;
      _subscription = channel.stream.listen(
        _handleData,
        onError: _handleError,
        onDone: _handleDone,
        cancelOnError: false,
      );
      // When the backend requires auth the token must be the very first frame,
      // ahead of any command. Buffering it on the sink now guarantees it is
      // sent first once the handshake completes. An empty token means the
      // backend is open, so nothing is sent.
      final authToken = token.trim();
      if (authToken.isNotEmpty) {
        channel.sink.add(jsonEncode(<String, dynamic>{
          'type': 'auth',
          'token': authToken,
        }));
      }
      // ready resolves once the handshake completes, or throws on failure.
      channel.ready.then((_) {
        _setState(AtlasConnectionState.connected);
      }).catchError((Object error) {
        _lastError = error.toString();
        _setState(AtlasConnectionState.error);
      });
    } catch (e) {
      _lastError = e.toString();
      _setState(AtlasConnectionState.error);
    }
  }

  /// Sends a natural language command to the agent as
  /// {"type":"command","command":...}.
  void sendCommand(String command) {
    final trimmed = command.trim();
    if (trimmed.isEmpty) return;
    if (!_canSend) {
      _pushLocalError('Not connected to ATLAS. Check the connection first.');
      return;
    }
    _channel!.sink.add(jsonEncode(<String, dynamic>{
      'type': 'command',
      'command': trimmed,
    }));
  }

  /// Previews a command without executing it, sending
  /// {"type":"plan","command":...}. The backend replies with a "plan" array
  /// and a "dry run" detail. Uses the same guards as [sendCommand] and never
  /// throws.
  void sendPlan(String command) {
    final trimmed = command.trim();
    if (trimmed.isEmpty) return;
    if (!_canSend) {
      _pushLocalError('Not connected to ATLAS. Check the connection first.');
      return;
    }
    _channel!.sink.add(jsonEncode(<String, dynamic>{
      'type': 'plan',
      'command': trimmed,
    }));
  }

  /// Asks the agent to stop the current task as {"type":"stop"}.
  void stop() {
    if (!_canSend) return;
    _channel!.sink.add(jsonEncode(<String, dynamic>{'type': 'stop'}));
  }

  /// Closes the socket cleanly and returns to the disconnected state.
  void disconnect() {
    _teardown();
    _setState(AtlasConnectionState.disconnected);
  }

  /// Clears the accumulated event history.
  void clearEvents() {
    if (_events.isEmpty) return;
    _events.clear();
    notifyListeners();
  }

  // ---- Internals ---------------------------------------------------------

  bool get _canSend =>
      _channel != null &&
      _connectionState != AtlasConnectionState.disconnected &&
      _connectionState != AtlasConnectionState.error;

  void _handleData(dynamic data) {
    final raw = data is String ? data : data.toString();
    final event = AtlasEvent.fromRaw(raw);
    // Receiving data implies the socket is live.
    if (_connectionState != AtlasConnectionState.connected) {
      _connectionState = AtlasConnectionState.connected;
    }
    _appendEvent(event);
  }

  void _handleError(Object error, [StackTrace? stackTrace]) {
    _lastError = error.toString();
    _setState(AtlasConnectionState.error);
  }

  void _handleDone() {
    // A close that follows an error keeps the error state; otherwise the
    // server or network simply went away and we are disconnected.
    if (_connectionState != AtlasConnectionState.error) {
      _setState(AtlasConnectionState.disconnected);
    }
  }

  void _pushLocalError(String message) {
    _lastError = message;
    _appendEvent(AtlasEvent(type: AtlasEventType.error, message: message));
  }

  void _appendEvent(AtlasEvent event) {
    _events.add(event);
    if (_events.length > _maxEvents) {
      _events.removeRange(0, _events.length - _maxEvents);
    }
    notifyListeners();
  }

  void _teardown() {
    _subscription?.cancel();
    _subscription = null;
    final channel = _channel;
    _channel = null;
    if (channel != null) {
      // Closing the sink also closes the underlying socket.
      channel.sink.close(ws_status.normalClosure);
    }
  }

  void _setState(AtlasConnectionState newState) {
    if (_connectionState == newState) return;
    _connectionState = newState;
    notifyListeners();
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _channel?.sink.close(ws_status.normalClosure);
    super.dispose();
  }
}
