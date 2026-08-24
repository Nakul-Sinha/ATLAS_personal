import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/atlas_service.dart';

/// SharedPreferences keys and defaults for the persisted connection settings.
/// Shared with the startup flow in main.dart.
const String kAtlasHostKey = 'atlas_host';
const String kAtlasPortKey = 'atlas_port';
const int kAtlasDefaultPort = 8000;

/// Lets the user enter the ATLAS backend host and port, verifies reachability
/// with a health check, persists the values, and pops back with `true` on
/// success so the caller can open the socket.
class ConnectionScreen extends StatefulWidget {
  const ConnectionScreen({super.key, required this.service});

  final AtlasService service;

  @override
  State<ConnectionScreen> createState() => _ConnectionScreenState();
}

class _ConnectionScreenState extends State<ConnectionScreen> {
  final TextEditingController _hostController = TextEditingController();
  final TextEditingController _portController =
      TextEditingController(text: '$kAtlasDefaultPort');

  bool _checking = false;
  String? _statusMessage;
  bool _lastAttemptOk = false;

  @override
  void initState() {
    super.initState();
    _loadSaved();
  }

  Future<void> _loadSaved() async {
    final prefs = await SharedPreferences.getInstance();
    final host = prefs.getString(kAtlasHostKey) ?? '';
    final port = prefs.getInt(kAtlasPortKey) ?? kAtlasDefaultPort;
    if (!mounted) return;
    setState(() {
      _hostController.text = host;
      _portController.text = '$port';
    });
  }

  @override
  void dispose() {
    _hostController.dispose();
    _portController.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    final host = _hostController.text.trim();
    final portText = _portController.text.trim();

    if (host.isEmpty) {
      setState(() {
        _statusMessage = 'Enter the PC IP address (run ipconfig to find it).';
        _lastAttemptOk = false;
      });
      return;
    }
    final port = int.tryParse(portText);
    if (port == null || port < 1 || port > 65535) {
      setState(() {
        _statusMessage = 'Enter a valid port between 1 and 65535.';
        _lastAttemptOk = false;
      });
      return;
    }

    setState(() {
      _checking = true;
      _statusMessage = 'Contacting ATLAS at $host:$port ...';
      _lastAttemptOk = false;
    });

    widget.service.configure(host, port);
    final ok = await widget.service.checkHealth();
    if (!mounted) return;

    if (ok) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(kAtlasHostKey, host);
      await prefs.setInt(kAtlasPortKey, port);
      if (!mounted) return;
      setState(() {
        _checking = false;
        _statusMessage = 'Connected to ATLAS.';
        _lastAttemptOk = true;
      });
      Navigator.of(context).pop(true);
    } else {
      setState(() {
        _checking = false;
        _statusMessage = widget.service.lastError != null
            ? 'Could not reach ATLAS: ${widget.service.lastError}'
            : 'Could not reach ATLAS at $host:$port.';
        _lastAttemptOk = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0E1116),
      body: Stack(
        fit: StackFit.expand,
        children: [
          Positioned.fill(
            child: Image.asset(
              'assets/bg.png',
              fit: BoxFit.cover,
              filterQuality: FilterQuality.none,
            ),
          ),
          SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Image.asset(
                      'assets/owl.png',
                      height: 64,
                      filterQuality: FilterQuality.none,
                    ),
                    const SizedBox(height: 16),
                    Container(
                      constraints: const BoxConstraints(maxWidth: 360),
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        color: const Color(0xF2FFFFFF),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: const Color(0xFF2B2B2B),
                          width: 2,
                        ),
                      ),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          const Text(
                            'Connect to ATLAS',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontFamily: 'Courier',
                              fontSize: 22,
                              fontWeight: FontWeight.bold,
                              color: Color(0xFF1A1A1A),
                            ),
                          ),
                          const SizedBox(height: 4),
                          const Text(
                            'Enter your PC IP address and port.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontFamily: 'Courier',
                              fontSize: 13,
                              color: Color(0xFF4A4A4A),
                            ),
                          ),
                          const SizedBox(height: 20),
                          TextField(
                            controller: _hostController,
                            keyboardType: TextInputType.url,
                            autocorrect: false,
                            enableSuggestions: false,
                            textInputAction: TextInputAction.next,
                            decoration: const InputDecoration(
                              labelText: 'Host / IP address',
                              hintText: '192.168.1.20',
                              border: OutlineInputBorder(),
                            ),
                          ),
                          const SizedBox(height: 12),
                          TextField(
                            controller: _portController,
                            keyboardType: TextInputType.number,
                            inputFormatters: <TextInputFormatter>[
                              FilteringTextInputFormatter.digitsOnly,
                            ],
                            textInputAction: TextInputAction.done,
                            onSubmitted: (_) => _connect(),
                            decoration: const InputDecoration(
                              labelText: 'Port',
                              hintText: '8000',
                              border: OutlineInputBorder(),
                            ),
                          ),
                          const SizedBox(height: 16),
                          SizedBox(
                            height: 46,
                            child: ElevatedButton(
                              onPressed: _checking ? null : _connect,
                              style: ElevatedButton.styleFrom(
                                backgroundColor: const Color(0xFF1F6FEB),
                                foregroundColor: Colors.white,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(8),
                                ),
                              ),
                              child: _checking
                                  ? const SizedBox(
                                      height: 20,
                                      width: 20,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        color: Colors.white,
                                      ),
                                    )
                                  : const Text(
                                      'Connect',
                                      style: TextStyle(
                                        fontFamily: 'Courier',
                                        fontSize: 16,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                            ),
                          ),
                          if (_statusMessage != null) ...<Widget>[
                            const SizedBox(height: 14),
                            Text(
                              _statusMessage!,
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontFamily: 'Courier',
                                fontSize: 13,
                                color: _lastAttemptOk
                                    ? const Color(0xFF1B7F3B)
                                    : const Color(0xFFB00020),
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
