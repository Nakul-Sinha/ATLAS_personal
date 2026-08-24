import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

/// A backend host found on the local network during a scan.
class DiscoveredHost {
  const DiscoveredHost({required this.host, required this.name});

  /// The IPv4 address the backend answered on, for example "192.168.1.20".
  final String host;

  /// The name the backend reported in its /companion response, normally
  /// "ATLAS".
  final String name;

  @override
  bool operator ==(Object other) =>
      other is DiscoveredHost && other.host == host && other.name == name;

  @override
  int get hashCode => Object.hash(host, name);
}

/// Signature for scan progress updates. [scanned] of [total] hosts have been
/// probed; [found] is non null on the tick where a matching host was
/// discovered.
typedef DiscoveryProgress = void Function(
  int scanned,
  int total,
  DiscoveredHost? found,
);

/// Scans the device's local IPv4 subnet for the ATLAS backend.
///
/// It derives the /24 subnet from the device's own address, then probes every
/// host from x.y.z.1 through x.y.z.254 by requesting `/companion` and keeping
/// the hosts that answer with JSON whose `name` matches [expectedName]. Probes
/// run with bounded concurrency and a short per host timeout. Nothing here ever
/// throws: unreachable hosts, timeouts, and malformed replies are treated as a
/// simple "no match".
class DiscoveryService {
  DiscoveryService({
    this.expectedName = 'ATLAS',
    this.concurrency = 32,
  });

  /// The value the backend must report in its `name` field to count as a match.
  /// Compared case insensitively after trimming.
  final String expectedName;

  /// How many hosts to probe at the same time.
  final int concurrency;

  bool _cancelled = false;

  /// Requests that an in-progress [scan] stop as soon as possible. A scan can be
  /// run again afterwards.
  void cancel() {
    _cancelled = true;
  }

  /// Probes the local subnet and returns the matching hosts.
  ///
  /// [port] is the backend port to try (default 8000). [timeout] bounds each
  /// individual probe. [onProgress] is called after every host is probed. If
  /// the local subnet cannot be determined the returned list is empty and
  /// [onProgress] is called once with a total of 0.
  Future<List<DiscoveredHost>> scan({
    int port = 8000,
    Duration timeout = const Duration(milliseconds: 400),
    DiscoveryProgress? onProgress,
  }) async {
    _cancelled = false;
    final results = <DiscoveredHost>[];

    final subnet = await _localSubnet();
    if (subnet == null) {
      onProgress?.call(0, 0, null);
      return results;
    }

    final hosts = <String>[
      for (int i = 1; i <= 254; i++) '$subnet.$i',
    ];
    final total = hosts.length;
    var scanned = 0;
    var nextIndex = 0;

    Future<void> worker() async {
      while (true) {
        if (_cancelled) return;
        // Reading and advancing the shared cursor happens synchronously, with
        // no await in between, so no two workers ever grab the same index.
        if (nextIndex >= hosts.length) return;
        final host = hosts[nextIndex++];

        final found = await _probe(host, port, timeout);
        scanned++;
        if (found != null) {
          results.add(found);
        }
        onProgress?.call(scanned, total, found);
      }
    }

    final workerCount = concurrency < total ? concurrency : total;
    final workers = <Future<void>>[
      for (int i = 0; i < workerCount; i++) worker(),
    ];
    await Future.wait(workers);
    return results;
  }

  /// Sends a single `/companion` request and returns a [DiscoveredHost] when the
  /// reply looks like ATLAS. Returns null for any failure or non match.
  Future<DiscoveredHost?> _probe(
    String host,
    int port,
    Duration timeout,
  ) async {
    final client = http.Client();
    try {
      final uri = Uri.parse('http://$host:$port/companion');
      final response = await client.get(uri).timeout(timeout);
      if (response.statusCode != 200) return null;
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic>) {
        final name = decoded['name'];
        if (name is String &&
            name.trim().toUpperCase() == expectedName.trim().toUpperCase()) {
          return DiscoveredHost(host: host, name: name.trim());
        }
      }
      return null;
    } catch (_) {
      // Timeouts, refused connections, malformed JSON: all mean "not ATLAS".
      return null;
    } finally {
      client.close();
    }
  }

  /// Finds the first three octets of a usable local IPv4 address, preferring
  /// private ranges. Returns null if no suitable address is found.
  Future<String?> _localSubnet() async {
    try {
      final interfaces = await NetworkInterface.list(
        includeLoopback: false,
        type: InternetAddressType.IPv4,
      );
      String? fallback;
      for (final interface in interfaces) {
        for (final address in interface.addresses) {
          final ip = address.address;
          if (address.isLoopback) continue;
          if (ip.startsWith('169.254.')) continue; // link-local, no gateway
          if (_isPrivate(ip)) {
            return _subnetOf(ip);
          }
          fallback ??= ip;
        }
      }
      if (fallback != null) return _subnetOf(fallback);
      return null;
    } catch (_) {
      return null;
    }
  }

  static String? _subnetOf(String ip) {
    final parts = ip.split('.');
    if (parts.length != 4) return null;
    return '${parts[0]}.${parts[1]}.${parts[2]}';
  }

  static bool _isPrivate(String ip) {
    if (ip.startsWith('192.168.')) return true;
    if (ip.startsWith('10.')) return true;
    final parts = ip.split('.');
    if (parts.length == 4 && parts[0] == '172') {
      final second = int.tryParse(parts[1]);
      if (second != null && second >= 16 && second <= 31) return true;
    }
    return false;
  }
}
