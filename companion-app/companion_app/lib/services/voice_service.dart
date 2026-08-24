import 'package:permission_handler/permission_handler.dart';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

/// Signature for a listener that is notified when the recognizer starts or
/// stops actively listening. Handy for keeping a UI indicator in sync with the
/// real plugin state, including when listening ends on its own after a pause.
typedef VoiceStatusChanged = void Function(bool isListening);

/// A small, defensive wrapper around the speech_to_text plugin.
///
/// Every method swallows plugin and permission failures and simply reports an
/// unavailable device rather than throwing, so callers can wire it into the UI
/// without extra guarding. Microphone permission is requested up front through
/// permission_handler before the plugin is initialized.
class VoiceService {
  VoiceService({this.onStatusChanged});

  /// Optional callback invoked whenever the underlying recognizer transitions
  /// between listening and not listening. Not required to use the service; the
  /// [isListening] getter reflects the same state on demand.
  final VoiceStatusChanged? onStatusChanged;

  final SpeechToText _speech = SpeechToText();

  bool _available = false;

  /// Whether the device has a working speech recognizer and permission was
  /// granted. False until [init] has completed successfully.
  bool get isAvailable => _available;

  /// Whether the recognizer is currently capturing audio.
  bool get isListening => _speech.isListening;

  /// Requests microphone permission and initializes the speech plugin.
  ///
  /// Returns true when speech recognition is ready to use. Safe to call more
  /// than once; the plugin caches its own initialization. Never throws.
  Future<bool> init() async {
    try {
      final status = await Permission.microphone.request();
      if (!status.isGranted) {
        _available = false;
        return false;
      }
      _available = await _speech.initialize(
        onError: _handleError,
        onStatus: _handleStatus,
      );
    } catch (_) {
      _available = false;
    }
    return _available;
  }

  /// Begins listening and streams transcripts to [onResult].
  ///
  /// [onResult] is called repeatedly with the best transcript so far and a flag
  /// that is true once the recognizer considers the phrase final. If the device
  /// is not ready yet this first tries to [init]. Never throws; if listening
  /// cannot start it simply returns.
  Future<void> startListening(
    void Function(String transcript, bool isFinal) onResult,
  ) async {
    if (!_available) {
      final ready = await init();
      if (!ready) return;
    }
    if (_speech.isListening) return;
    try {
      await _speech.listen(
        onResult: (SpeechRecognitionResult result) {
          onResult(result.recognizedWords, result.finalResult);
        },
        listenFor: const Duration(seconds: 30),
        pauseFor: const Duration(seconds: 4),
        listenOptions: SpeechListenOptions(
          partialResults: true,
          cancelOnError: true,
          listenMode: ListenMode.dictation,
        ),
      );
    } catch (_) {
      // Ignore: startListening must never throw. The status listener will keep
      // any UI indicator consistent.
    }
  }

  /// Stops listening and keeps whatever has been transcribed so far. Never
  /// throws.
  Future<void> stop() async {
    try {
      if (_speech.isListening) {
        await _speech.stop();
      }
    } catch (_) {
      // Ignore: stopping is best effort.
    }
  }

  void _handleStatus(String status) {
    final listening = status == SpeechToText.listeningStatus;
    onStatusChanged?.call(listening);
  }

  void _handleError(SpeechRecognitionError error) {
    // A recognizer error means we are no longer listening. Surface that so the
    // UI can drop any listening indicator.
    onStatusChanged?.call(false);
  }
}
