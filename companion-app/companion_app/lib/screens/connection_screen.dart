import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/atlas_service.dart';
import '../services/discovery_service.dart';

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

  /// Local network auto-discovery for finding the ATLAS backend.
  final DiscoveryService _discovery = DiscoveryService();
  bool _scanning = false;
  int _scanScanned = 0;
  int _scanTotal = 0;
  String? _scanMessage;
  final List<DiscoveredHost> _found = <DiscoveredHost>[];

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
    _discovery.cancel();
    _hostController.dispose();
    _portController.dispose();
    super.dispose();
  }

  /// Scans the local network for the ATLAS backend and lists any hosts found.
  Future<void> _scan() async {
    if (_scanning) return;

    final portText = _portController.text.trim();
    final port = int.tryParse(portText) ?? kAtlasDefaultPort;

    setState(() {
      _scanning = true;
      _found.clear();
      _scanScanned = 0;
      _scanTotal = 0;
      _statusMessage = null;
      _scanMessage = 'Scanning your network for ATLAS ...';
    });

    final results = await _discovery.scan(
      port: port,
      onProgress: (scanned, total, found) {
        if (!mounted) return;
        setState(() {
          _scanScanned = scanned;
          _scanTotal = total;
          if (found != null && !_found.contains(found)) {
            _found.add(found);
          }
        });
      },
    );

    if (!mounted) return;
    setState(() {
      _scanning = false;
      if (_scanTotal == 0) {
        _scanMessage =
            'Could not determine your local network. Enter the IP manually.';
      } else if (results.isEmpty) {
        _scanMessage =
            'No ATLAS backend found on this network. Enter the IP manually.';
      } else {
        final plural = results.length == 1 ? '' : 's';
        _scanMessage = 'Found ${results.length} ATLAS host$plural. Tap to use.';
      }
    });
  }

  /// Fills the host field with a discovered address. The port stays editable.
  void _selectHost(DiscoveredHost host) {
    setState(() {
      _hostController.text = host.host;
      _scanMessage = 'Selected ${host.host}. Tap Connect to finish.';
      _statusMessage = null;
    });
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
                          const SizedBox(height: 18),
                          const Divider(
                            height: 1,
                            thickness: 1,
                            color: Color(0x332B2B2B),
                          ),
                          const SizedBox(height: 16),
                          const Text(
                            "Don't know the IP?",
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontFamily: 'Courier',
                              fontSize: 13,
                              color: Color(0xFF4A4A4A),
                            ),
                          ),
                          const SizedBox(height: 10),
                          SizedBox(
                            height: 46,
                            child: OutlinedButton.icon(
                              onPressed:
                                  (_scanning || _checking) ? null : _scan,
                              style: OutlinedButton.styleFrom(
                                foregroundColor: const Color(0xFF1F6FEB),
                                side: const BorderSide(
                                  color: Color(0xFF1F6FEB),
                                  width: 2,
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(8),
                                ),
                              ),
                              icon: _scanning
                                  ? const SizedBox(
                                      height: 18,
                                      width: 18,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        color: Color(0xFF1F6FEB),
                                      ),
                                    )
                                  : const Icon(Icons.wifi_find, size: 20),
                              label: Text(
                                _scanning ? 'Scanning...' : 'Scan for ATLAS',
                                style: const TextStyle(
                                  fontFamily: 'Courier',
                                  fontSize: 15,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                          ),
                          if (_scanning && _scanTotal > 0) ...<Widget>[
                            const SizedBox(height: 12),
                            LinearProgressIndicator(
                              value: _scanScanned / _scanTotal,
                              minHeight: 6,
                              backgroundColor: const Color(0x332B2B2B),
                              color: const Color(0xFF1F6FEB),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              'Checked $_scanScanned of $_scanTotal addresses',
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                fontFamily: 'Courier',
                                fontSize: 12,
                                color: Color(0xFF4A4A4A),
                              ),
                            ),
                          ],
                          if (_scanMessage != null) ...<Widget>[
                            const SizedBox(height: 12),
                            Text(
                              _scanMessage!,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                fontFamily: 'Courier',
                                fontSize: 13,
                                color: Color(0xFF1A1A1A),
                              ),
                            ),
                          ],
                          if (_found.isNotEmpty) ...<Widget>[
                            const SizedBox(height: 10),
                            for (final host in _found)
                              Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: _DiscoveredHostTile(
                                  host: host,
                                  onTap: () => _selectHost(host),
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

/// A tappable row for a host found during a network scan. Tapping it fills the
/// host field on the connection screen.
class _DiscoveredHostTile extends StatelessWidget {
  const _DiscoveredHostTile({required this.host, required this.onTap});

  final DiscoveredHost host;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: const Color(0xFFF2F6FF),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: const Color(0xFF1F6FEB), width: 1.5),
        ),
        child: Row(
          children: [
            const Icon(
              Icons.computer,
              size: 20,
              color: Color(0xFF1F6FEB),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    host.name,
                    style: const TextStyle(
                      fontFamily: 'Courier',
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF1A1A1A),
                    ),
                  ),
                  Text(
                    host.host,
                    style: const TextStyle(
                      fontFamily: 'Courier',
                      fontSize: 12,
                      color: Color(0xFF4A4A4A),
                    ),
                  ),
                ],
              ),
            ),
            const Icon(
              Icons.arrow_forward_ios,
              size: 14,
              color: Color(0xFF1F6FEB),
            ),
          ],
        ),
      ),
    );
  }
}
