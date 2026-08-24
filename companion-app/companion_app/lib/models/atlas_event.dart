import 'dart:convert';

/// The category of a message received from the ATLAS backend over the
/// WebSocket connection.
enum AtlasEventType { progress, result, error, unknown }

/// A single, typed message from the ATLAS backend.
///
/// The backend sends JSON frames shaped like:
///   {"type":"progress","step":"action","status":"executing","detail":"..."}
///   {"type":"result","success":true,"detail":"..."}
///   {"type":"error","message":"..."}
///
/// All fields are optional because a given frame only carries the subset that
/// is relevant to its [type]. Parsing never throws: malformed input becomes an
/// error typed event instead.
class AtlasEvent {
  AtlasEvent({
    required this.type,
    this.step,
    this.status,
    this.detail,
    this.message,
    this.success,
    DateTime? timestamp,
  }) : timestamp = timestamp ?? DateTime.now();

  final AtlasEventType type;
  final String? step;
  final String? status;
  final String? detail;
  final String? message;
  final bool? success;
  final DateTime timestamp;

  /// Builds an [AtlasEvent] from an already decoded JSON map. Unknown or
  /// missing fields are tolerated and left null.
  factory AtlasEvent.fromJson(Map<String, dynamic> json) {
    final rawType = json['type'];
    final type = switch (rawType) {
      'progress' => AtlasEventType.progress,
      'result' => AtlasEventType.result,
      'error' => AtlasEventType.error,
      _ => AtlasEventType.unknown,
    };
    final rawSuccess = json['success'];
    return AtlasEvent(
      type: type,
      step: json['step']?.toString(),
      status: json['status']?.toString(),
      detail: json['detail']?.toString(),
      message: json['message']?.toString(),
      success: rawSuccess is bool ? rawSuccess : null,
    );
  }

  /// Parses a raw text frame into an [AtlasEvent]. Returns an error typed
  /// event if the frame is not valid JSON or is not a JSON object.
  factory AtlasEvent.fromRaw(String raw) {
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic>) {
        return AtlasEvent.fromJson(decoded);
      }
      return AtlasEvent(type: AtlasEventType.unknown, detail: raw);
    } catch (_) {
      return AtlasEvent(
        type: AtlasEventType.error,
        message: 'Received a malformed message from ATLAS',
      );
    }
  }

  /// Whether this event represents work that is still ongoing.
  bool get isInProgress =>
      type == AtlasEventType.progress &&
      (status == null || status == 'executing' || status == 'running');

  /// Whether this event represents a terminal error or a failed result.
  bool get isError => type == AtlasEventType.error || success == false;

  /// A short human readable line suitable for display in the UI.
  String get displayText {
    switch (type) {
      case AtlasEventType.progress:
        final String label =
            (step != null && step!.isNotEmpty) ? step! : 'working';
        final String? body =
            (detail != null && detail!.isNotEmpty) ? detail : status;
        if (body != null && body.isNotEmpty) {
          return '$label: $body';
        }
        return label;
      case AtlasEventType.result:
        final String prefix = success == false ? 'Finished' : 'Done';
        return (detail != null && detail!.isNotEmpty)
            ? '$prefix: $detail'
            : prefix;
      case AtlasEventType.error:
        return (message != null && message!.isNotEmpty)
            ? 'Error: $message'
            : 'An error occurred';
      case AtlasEventType.unknown:
        return (detail != null && detail!.isNotEmpty)
            ? detail!
            : 'Message received';
    }
  }
}
