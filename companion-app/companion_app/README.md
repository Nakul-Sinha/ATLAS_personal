# companion_app

The ATLAS Flutter companion app. It connects to the ATLAS backend over your
local network, sends natural language commands, and streams live progress back
to your phone.

## What it does

- Verifies the backend with an HTTP health check.
- Opens a WebSocket to the backend and shows progress, results, and errors.
- Remembers the last host and port you used.

## Setting the connection

The app talks to the ATLAS backend (a FastAPI server, default port 8000) running
on your PC. The phone and the PC must be on the same network.

1. On the PC running ATLAS, find its IPv4 address.
   - Windows: open a terminal and run `ipconfig`, then read the "IPv4 Address"
     value (something like `192.168.1.20`).
   - macOS or Linux: run `ifconfig` or `ip addr`.
2. Make sure the ATLAS backend is running and listening on port 8000.
3. Launch the companion app. On first launch it opens the connection screen.
   You can reopen it any time from the status chip in the top right of the home
   screen.
4. Enter the PC IPv4 address in the Host field and the port (8000 by default),
   then tap Connect. The app runs a health check and, on success, saves the
   values and returns to the home screen.
5. Type a command in the search box (for example "Open Notepad and type hello")
   and submit it. Progress appears below as the agent works.

Note: the app uses plain `http://` and `ws://` on the local network, so Android
cleartext traffic is enabled in the manifest.

## Running the app

From this directory (`companion-app/companion_app`):

```
flutter pub get
flutter run
```

`flutter pub get` fetches the dependencies (`web_socket_channel`, `http`, and
`shared_preferences`). `flutter run` builds and launches the app on a connected
device or emulator.

## Project layout

- `lib/main.dart` - app entry point, home screen, and progress UI.
- `lib/services/atlas_service.dart` - backend client (health check plus
  WebSocket command and progress stream).
- `lib/models/atlas_event.dart` - typed model for backend messages.
- `lib/screens/connection_screen.dart` - host and port entry with persistence.
- `lib/executing_card.dart` - presentational progress card.
