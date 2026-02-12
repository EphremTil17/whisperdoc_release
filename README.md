# WhisperDoc Flutter Client v2.22.2 (Pub Repo)

### NOT SOURCE CODE - For Public Release Only

<img width="3375" height="3363" alt="WhisperDoc Github Preview" src="https://github.com/user-attachments/assets/661f6737-b885-4d5d-b2a7-91ce8392a0de" />

## 
A native Windows desktop application for real-time speech-to-text dictation powered by OpenAI's Whisper model.


https://github.com/user-attachments/assets/a6034fd9-7f4b-4279-9e5b-acfc6238f626


## Purpose

WhisperDoc Client provides a lightweight, always-ready interface for voice dictation. It captures audio from your microphone, streams it to a local Whisper backend server, and receives transcriptions in real-time. The transcribed text can be automatically copied to your clipboard and pasted into any application.

This client is designed for users who need fast, accurate dictation without leaving their current workflow. Press a global hotkey, speak, and your words appear wherever your cursor is.

## 🔒 Enterprise-Grade Security (Hardened v2.13.0)

The Flutter client has been hardened to match server-side security standards through five core pillars:

- **Identity Federation (OIDC/PKCE)**: Implements industry-standard OAuth2 PKCE (Proof Key for Code Exchange) flow via the **System Browser**. Verified via a custom Dart implementation for maximum transparency and Windows compatibility.
- **Credential Isolation**: API keys and OIDC JWTs are stored exclusively in the **Windows Credential Manager** (Secure Vault). Sensitive tokens are never written to plain-text configuration files.
- **Transport Security & RFC 1918**: Mandatory `wss://` (TLS 1.2+) is enforced for all public connections. Plain-text `ws://` is permitted **only** after validating the target as a verified local private network IP (RFC 1918).
- **Hardened Handshake (Handshake Cage)**: Implements a strict state machine that buffers audio locally and only flushes to the socket *after* the identity-verified handshake is acknowledged by the backend.
- **Active Defense Awareness**: Intelligently handles `1008` (Policy Violation) closures. The UI provides real-time "Ban Cooldown" countdowns and respects server-mandated wait periods.
- **Data-at-Rest Encryption**: Transcription history is stored in an **AES-256 encrypted Isar database**. Encryption keys are derived uniquely per-installation using hardware-bound salts and PBKDF2.
- **Memory Hygiene**: Toggleable **Incognito Mode** ensures zero-persistence on the backend (Ghost Mode) and performs explicit RAM clearing of sensitive transcription buffers on the client.

The client follows a **Smart Modular Architecture** designed for high scalability and zero-latency performance:

```
lib/
├── controllers/      # State orchestration (RecordingController)
├── infrastructure/   # System foundations (DI, Theme, Constants)
├── logic/            # Pure domain logic (Processors, Mappers, Models)
├── services/         # Functional domain specialized services
│   ├── auth/         # OIDC & Session management
│   ├── hardware/     # Audio capture & Hotkey listeners
│   ├── transport/    # WebSocket orchestration & Handshake
│   └── utility/      # Logging, Secure Vault, Settings
├── ui/               # Presentation layer
│   ├── features/     # Feature modules (recording, settings)
│   ├── screens/      # Main screens & contextual dialogs
│   └── shared/       # Global widgets & theme tokens
└── main.dart         # Clean entry point with service bootstrap
```

### Key Design Principles

- **Dependency Injection**: Uses `get_it` for service location and clean testability.
- **Single Source of Truth**: Controllers own state and listen to underlying services.
- **Immutable Isolate Pattern**: Hotkey listener respawns on settings change for clean state.
- **Native Win32 Integration**: Direct API calls for clipboard, hotkeys, and keyboard simulation.
- **Zero-Trust Networking**: Validates server parity during the versioned handshake.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | Flutter 3.x (Windows) |
| State Management | Provider + ChangeNotifier |
| Database | Isar (AES-256 Encrypted) |
| Secure Storage | flutter_secure_storage (WinCred) |
| Networking | WebSocket (web_socket_channel) |
| Native APIs | Win32 via ffi/win32 packages |
| Encryption | encrypt (AES/CBC) |

- **Instantaneous Connection**: Implements a "Zero-Latency" recording flow. Audio capture and UI feedback initiate instantly while the WebSocket handshake completes in parallel.
- **Background Auto-Wake**: The transport layer automatically resumes connectivity when a recording is initiated, removing the need for manual connection management.
- **Advanced Security Indicators**: Visual feedback (Lock/Warning/Block) for connection security status.
- **JWT Expiry Warnings**: Automatic detection of session tokens with user-friendly expiry countdowns.
- **Deep Sleep Proof Hotkeys**: Native `GetMessage` blocking loop ensures hotkeys work after system sleep.
- **Global Hotkey**: Trigger recording from any application (default: Ctrl+Alt+E).
- **Auto Copy/Paste**: Automatically insert transcriptions at your cursor.
- **WebSocket Resilience**: Exponential backoff reconnection with ban-awareness.
- **Intelligent Idle Timeout**: Connection auto-closes after inactivity to save resources.
- **Incognito Mode**: Protocol-level privacy flag with memory hygiene.
- **Verification Suite**: Modular security tests (`auth_service_test.dart`) validating PKCE integrity and state-parameter protection.
- **Glassmorphic UI**: Modern, translucent design with integrated OIDC identity hardening.

## Prerequisites

- Windows 10/11
- Flutter SDK 3.x
- A running WhisperDoc backend server

## Quick Start

1. **Install dependencies**
   ```bash
   flutter pub get
   ```
2. **Configure Environment**
   Duplicate `env.json.template` to `env.json` and fill in your OIDC credentials.

3. **Run in development**
   ```bash
   flutter run -d windows --dart-define-from-file=env.json
   ```
4. **Build release**
   ```bash
   flutter build windows --release --obfuscate --split-debug-info=build/debug-info --dart-define-from-file=env.json
   ```

## Configuration

Access settings via the gear icon or hamburger menu:

- **Server URI**: WebSocket endpoint (e.g., `ws://localhost:9989/ws`).
- **Secure Key**: Enter your API Key or JWT (stored in Windows Credential Manager).
- **Global Hotkey**: Customize your trigger key combination.
- **Auto Copy/Paste**: Control automation behavior.

## Known Limitations

### Hot Reload Does Not Work During Development

Due to the use of native Win32 blocking calls (`GetMessage`) in the hotkey isolate, **hot reload will hang indefinitely**. This is a trade-off for having bulletproof, deep-sleep-resistant hotkey handling.

**Workarounds:**
- Use **Hot Restart** (`Shift+R` in terminal) instead of hot reload.
- Press the hotkey before attempting hot reload (unblocks the isolate momentarily).
- Full app restart (`q` to stop, then `flutter run` again).

> **Note**: This limitation only affects development. Production builds are unaffected.

## Recent Improvements (v2.14.0)

### Performance & Stability
- **uvloop & orjson Support**: Client communication is now faster due to the backend's move to ultra-high performance I/O and JSON serialization.
- **Drift-Proof Handshake**: Handshake timing is more resilient to network jitter and backend scheduling.
- **Improved Resource Cleanup**: Accelerated model unloading and RAM reclamation on the backend reduces idle latency for new sessions.

## Older Improvements (v2.13.0)

### Hotkey Resilience
- Replaced `Timer.periodic` polling with native `GetMessage` blocking loop
- Hotkeys now work reliably after system sleep/hibernate
- Implemented "Immutable Isolate" pattern: service respawns on settings change

### WebSocket Resilience
- Fixed reconnection logic bug (status was checked after update, not before)
- Added exponential backoff for reconnections to prevent resource waste
- Idle timeout reduced to 3 minutes for faster resource cleanup

### OIDC Identity Integration
- Implemented manual OAuth2 PKCE flow for Windows compatibility
- Replaced third-party OIDC libraries with a lean Dart implementation
- Added **System Browser** authentication for enhanced user trust and security

### Security Hardening
- Implemented the **Handshake Cage** (buffer-then-flush) strategy
- Added OIDC session persistence using hardware-bound secure storage
- Explicitly masked sensitive authentication tokens in technical logs

### Architecture Refactoring
- Added `get_it` for dependency injection
- Created `AppConstants` for centralized configuration
- Moved `RecordingController` from UI layer to core layer
- Shifted to a **Templatized Configuration** using `String.fromEnvironment`
- Consolidated JWT logic using `jwt_decoder` and removed legacy `dart_jsonwebtoken`
- Implemented a Win32 Named Mutex to enforce single-instance integrity
- Created `GlassDialog` reusable widget (reduced dialog boilerplate by ~50 lines each)

## License

See the root project LICENSE file.
