import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'executing_card.dart';
import 'models/atlas_event.dart';
import 'screens/connection_screen.dart';
import 'services/atlas_service.dart';
import 'services/voice_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(AtlasApp(service: AtlasService()));
}

class AtlasApp extends StatelessWidget {
  AtlasApp({super.key, AtlasService? service})
      : service = service ?? AtlasService();

  /// Single shared service instance handed down through the widget tree.
  final AtlasService service;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'ATLAS',
      home: StartupGate(service: service),
    );
  }
}

/// Decides the first screen based on saved connection settings. If a host was
/// stored previously it configures the service and opens the socket; otherwise
/// it routes the user to the connection screen on first frame.
class StartupGate extends StatefulWidget {
  const StartupGate({super.key, required this.service});

  final AtlasService service;

  @override
  State<StartupGate> createState() => _StartupGateState();
}

class _StartupGateState extends State<StartupGate> {
  bool _loading = true;
  bool _hasSavedConnection = false;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    final prefs = await SharedPreferences.getInstance();
    final host = prefs.getString(kAtlasHostKey) ?? '';
    final port = prefs.getInt(kAtlasPortKey) ?? kAtlasDefaultPort;
    final hasSaved = host.isNotEmpty;
    if (hasSaved) {
      widget.service.configure(host, port);
    }
    if (!mounted) return;
    setState(() {
      _hasSavedConnection = hasSaved;
      _loading = false;
    });
    if (hasSaved) {
      // The host was verified previously, so try to open the socket now.
      widget.service.connect();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        backgroundColor: Colors.black,
        body: Center(child: CircularProgressIndicator()),
      );
    }
    return AtlasHome(
      service: widget.service,
      promptForConnection: !_hasSavedConnection,
    );
  }
}

/// Helper widget to render tiny pixel-art PNGs scaled up with nearest-neighbor
/// filtering so they stay crisp instead of blurry.
class PixelArt extends StatelessWidget {
  const PixelArt({
    super.key,
    required this.asset,
    this.width,
    this.height,
    this.fit = BoxFit.contain,
  });

  final String asset;
  final double? width;
  final double? height;
  final BoxFit fit;

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      asset,
      width: width,
      height: height,
      fit: fit,
      filterQuality: FilterQuality.none, // nearest-neighbor for pixel art
    );
  }
}

class AtlasHome extends StatefulWidget {
  const AtlasHome({
    super.key,
    required this.service,
    this.promptForConnection = false,
  });

  final AtlasService service;
  final bool promptForConnection;

  @override
  State<AtlasHome> createState() => _AtlasHomeState();
}

class _AtlasHomeState extends State<AtlasHome> {
  final TextEditingController _commandController = TextEditingController();

  /// Speech to text helper for dictating commands (issue CA-07). Created here
  /// so its status callback can drive the listening indicator.
  late final VoiceService _voiceService = VoiceService(
    onStatusChanged: _handleVoiceStatus,
  );
  bool _isListening = false;

  @override
  void initState() {
    super.initState();
    if (widget.promptForConnection) {
      // Open the connection screen after the first frame so a Navigator is
      // available above this widget.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _openConnectionScreen();
      });
    }
  }

  @override
  void dispose() {
    _voiceService.stop();
    _commandController.dispose();
    super.dispose();
  }

  /// Keeps the listening indicator in sync with the recognizer, including when
  /// it stops on its own after a pause.
  void _handleVoiceStatus(bool listening) {
    if (!mounted) return;
    if (_isListening != listening) {
      setState(() => _isListening = listening);
    }
  }

  /// Toggles dictation. While listening, partial transcripts fill the field
  /// live; the final transcript is left in place for the user to review and
  /// submit as usual.
  Future<void> _toggleListening() async {
    if (_isListening) {
      await _voiceService.stop();
      if (mounted) setState(() => _isListening = false);
      return;
    }

    final ready = await _voiceService.init();
    if (!mounted) return;
    if (!ready) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Voice input is unavailable. Check microphone permission.',
            style: TextStyle(fontFamily: 'Courier'),
          ),
        ),
      );
      return;
    }

    setState(() => _isListening = true);
    await _voiceService.startListening((transcript, isFinal) {
      if (!mounted) return;
      setState(() {
        _commandController.text = transcript;
        _commandController.selection = TextSelection.fromPosition(
          TextPosition(offset: _commandController.text.length),
        );
      });
    });
  }

  Future<void> _openConnectionScreen() async {
    final result = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => ConnectionScreen(service: widget.service),
      ),
    );
    if (result == true) {
      widget.service.connect();
    }
  }

  void _submitCommand() {
    final text = _commandController.text.trim();
    if (text.isEmpty) return;
    widget.service.sendCommand(text);
    _commandController.clear();
    FocusScope.of(context).unfocus();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      body: Stack(
        fit: StackFit.expand,
        children: [
          // 1. Background Layer
          Positioned.fill(
            child: Image.asset(
              'assets/bg.png',
              fit: BoxFit.cover,
              filterQuality: FilterQuality.none,
            ),
          ),
          // 2. Content Layer
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: 24.0,
                vertical: 10.0,
              ),
              child: Column(
                children: [
                  // Connection status chip, tap to open the connection screen.
                  Align(
                    alignment: Alignment.centerRight,
                    child: _ConnectionIndicator(
                      service: widget.service,
                      onTap: _openConnectionScreen,
                    ),
                  ),
                  const SizedBox(height: 6),
                  // Search Section
                  SizedBox(
                    height: 200, // Constrain search section height
                    child: Stack(
                      alignment: Alignment.topCenter,
                      clipBehavior: Clip.none, // Allows owl to overflow box
                      children: [
                        // The Search Box Wrapper
                        Padding(
                          padding: const EdgeInsets.only(top: 25.0), // Space for owl
                          child: Stack(
                            clipBehavior: Clip.none,
                            children: [
                              // The Search Box Image
                              Positioned.fill(
                                child: PixelArt(
                                  asset: 'assets/search_box.png',
                                  fit: BoxFit.contain,
                                ),
                              ),
                              // Text and Icon inside the box
                              Padding(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 25.0,
                                ),
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: TextField(
                                        controller: _commandController,
                                        textInputAction: TextInputAction.send,
                                        onSubmitted: (_) => _submitCommand(),
                                        style: const TextStyle(
                                          color: Color(0xFF1A1A1A),
                                          fontSize: 18,
                                          fontFamily: 'Courier',
                                        ),
                                        decoration: const InputDecoration(
                                          hintText: "Ask ATLAS anything...",
                                          border: InputBorder.none,
                                          hintStyle: TextStyle(
                                            color: Color(0xFF4A4A4A),
                                            fontSize: 18,
                                            fontFamily: 'Courier',
                                          ),
                                        ),
                                      ),
                                    ),
                                    // Microphone toggle for voice dictation.
                                    GestureDetector(
                                      onTap: _toggleListening,
                                      behavior: HitTestBehavior.opaque,
                                      child: Padding(
                                        padding: const EdgeInsets.only(
                                          right: 10.0,
                                        ),
                                        child: Icon(
                                          _isListening
                                              ? Icons.mic
                                              : Icons.mic_none,
                                          size: 22,
                                          color: _isListening
                                              ? const Color(0xFFB00020)
                                              : const Color(0xFF1A1A1A),
                                        ),
                                      ),
                                    ),
                                    GestureDetector(
                                      onTap: _submitCommand,
                                      behavior: HitTestBehavior.opaque,
                                      child: const PixelArt(
                                        asset: 'assets/search_icon.png',
                                        height: 20,
                                        width: 20,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                        // The Owl sitting on top
                        Positioned(
                          top: -12, // Move owl slightly upwards
                          child: PixelArt(
                            asset: 'assets/owl.png',
                            height: 55,
                          ),
                        ),
                        // Subtle listening indicator shown while dictating.
                        if (_isListening)
                          const Positioned(
                            bottom: 2,
                            child: _ListeningIndicator(),
                          ),
                      ],
                    ),
                  ),
                  // 3. Live progress area, driven by the service events.
                  Expanded(
                    child: ListenableBuilder(
                      listenable: widget.service,
                      builder: (context, _) => _ProgressView(
                        service: widget.service,
                        onStop: widget.service.stop,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// A small pill showing the current connection state, tappable to open the
/// connection screen. Rebuilds itself from the service.
class _ConnectionIndicator extends StatelessWidget {
  const _ConnectionIndicator({required this.service, required this.onTap});

  final AtlasService service;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: service,
      builder: (context, _) {
        final state = service.connectionState;
        Color color;
        String label;
        switch (state) {
          case AtlasConnectionState.connected:
            color = const Color(0xFF2ECC71);
            label = 'Connected';
            break;
          case AtlasConnectionState.connecting:
            color = const Color(0xFFF1C40F);
            label = 'Connecting';
            break;
          case AtlasConnectionState.error:
            color = const Color(0xFFE74C3C);
            label = 'Error';
            break;
          case AtlasConnectionState.disconnected:
            color = const Color(0xFF95A5A6);
            label = 'Disconnected';
            break;
        }
        return GestureDetector(
          onTap: onTap,
          behavior: HitTestBehavior.opaque,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: const Color(0xCC1A1A1A),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(
                    color: color,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  label,
                  style: const TextStyle(
                    color: Colors.white,
                    fontFamily: 'Courier',
                    fontSize: 12,
                  ),
                ),
                const SizedBox(width: 6),
                const Icon(Icons.settings, size: 14, color: Colors.white70),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// Renders the current agent progress. Shows the featured [ExecutingCard] for
/// the latest event plus a scrolling log of prior events.
class _ProgressView extends StatelessWidget {
  const _ProgressView({required this.service, required this.onStop});

  final AtlasService service;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final events = service.events;
    if (events.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Text(
            _emptyMessage(service.connectionState),
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontFamily: 'Courier',
              fontSize: 14,
              color: Color(0xFF2B2B2B),
            ),
          ),
        ),
      );
    }

    final latest = events.last;
    final showStop = service.isConnected && latest.isInProgress;

    return Column(
      children: [
        // Featured current status using the existing ExecutingCard widget.
        ExecutingCard(
          message: (latest.detail != null && latest.detail!.isNotEmpty)
              ? latest.detail!
              : latest.displayText,
          statusLabel: _statusLabel(latest),
        ),
        if (showStop)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: TextButton.icon(
              onPressed: onStop,
              icon: const Icon(Icons.stop_circle, color: Color(0xFFB00020)),
              label: const Text(
                'Stop',
                style: TextStyle(
                  fontFamily: 'Courier',
                  color: Color(0xFFB00020),
                ),
              ),
            ),
          ),
        const SizedBox(height: 8),
        // Scrolling log, newest first.
        Expanded(
          child: ListView.builder(
            reverse: true,
            itemCount: events.length,
            itemBuilder: (context, index) {
              final event = events[events.length - 1 - index];
              return _EventTile(event: event);
            },
          ),
        ),
      ],
    );
  }

  String _emptyMessage(AtlasConnectionState state) {
    switch (state) {
      case AtlasConnectionState.connected:
        return 'Connected. Type a command above to get started.';
      case AtlasConnectionState.connecting:
        return 'Connecting to ATLAS ...';
      case AtlasConnectionState.error:
        return 'Connection problem. Tap the status chip to reconnect.';
      case AtlasConnectionState.disconnected:
        return 'Not connected. Tap the status chip to set up your connection.';
    }
  }

  String _statusLabel(AtlasEvent event) {
    switch (event.type) {
      case AtlasEventType.progress:
        return 'Executing...';
      case AtlasEventType.result:
        return event.success == false ? 'Failed' : 'Done';
      case AtlasEventType.error:
        return 'Error';
      case AtlasEventType.unknown:
        return 'ATLAS';
    }
  }
}

/// A small pill with a gently pulsing red dot shown while the app is listening
/// for dictation. Kept subtle so it does not fight the pixel-art aesthetic.
class _ListeningIndicator extends StatefulWidget {
  const _ListeningIndicator();

  @override
  State<_ListeningIndicator> createState() => _ListeningIndicatorState();
}

class _ListeningIndicatorState extends State<_ListeningIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: const Color(0xCC1A1A1A),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          FadeTransition(
            opacity: Tween<double>(begin: 0.35, end: 1.0).animate(_controller),
            child: Container(
              width: 9,
              height: 9,
              decoration: const BoxDecoration(
                color: Color(0xFFB00020),
                shape: BoxShape.circle,
              ),
            ),
          ),
          const SizedBox(width: 8),
          const Text(
            'Listening...',
            style: TextStyle(
              color: Colors.white,
              fontFamily: 'Courier',
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}

/// A single line in the progress log.
class _EventTile extends StatelessWidget {
  const _EventTile({required this.event});

  final AtlasEvent event;

  @override
  Widget build(BuildContext context) {
    Color color;
    IconData icon;
    switch (event.type) {
      case AtlasEventType.progress:
        color = const Color(0xFF2B2B2B);
        icon = Icons.autorenew;
        break;
      case AtlasEventType.result:
        final failed = event.success == false;
        color = failed ? const Color(0xFFB00020) : const Color(0xFF1B7F3B);
        icon = failed ? Icons.error_outline : Icons.check_circle_outline;
        break;
      case AtlasEventType.error:
        color = const Color(0xFFB00020);
        icon = Icons.error_outline;
        break;
      case AtlasEventType.unknown:
        color = const Color(0xFF4A4A4A);
        icon = Icons.info_outline;
        break;
    }
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 3),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xE6FFFFFF),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0x332B2B2B)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              event.displayText,
              style: TextStyle(
                fontFamily: 'Courier',
                fontSize: 13,
                color: color,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
