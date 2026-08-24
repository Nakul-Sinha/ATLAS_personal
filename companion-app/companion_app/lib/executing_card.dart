import 'package:flutter/material.dart';

/// Presentational card that shows the owl, a pixel-art message box, and a
/// status line. Fed a [message] (the current detail) and an optional
/// [statusLabel] such as "Executing...", "Done", or "Error".
class ExecutingCard extends StatelessWidget {
  final String message;
  final String statusLabel;

  const ExecutingCard({
    super.key,
    required this.message,
    this.statusLabel = 'Executing...',
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Owl image, moved up so it perches on the message box.
          Transform.translate(
            offset: const Offset(0, -12),
            child: Image.asset(
              'assets/owl.png',
              width: 80,
              filterQuality: FilterQuality.none,
            ),
          ),
          const SizedBox(height: 16),
          // Message box with pixel-art background.
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
            ),
            child: Stack(
              alignment: Alignment.center,
              children: [
                Positioned.fill(
                  child: Image.asset(
                    'assets/component_box.png',
                    fit: BoxFit.fill,
                    filterQuality: FilterQuality.none,
                  ),
                ),
                Text(
                  message,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: 'monospace',
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          Text(statusLabel),
        ],
      ),
    );
  }
}
