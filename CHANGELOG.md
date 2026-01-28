# WhisperDoc Technical Changelog

## [2.20.0] - 2026-01-28
### Protocol & Security Engineering
- Standardized WebSocket 1008 rejections: Implemented a mandatory JSON error event transmission before socket closure to provide clients with explicit context (bans, versioning).
- Developed a Hardened Handshake Versioning Gate enforcing `MIN_CLIENT_VERSION` (strict block) and `SEC_CLIENT_VERSION` (advisory) logic.
- Integrated IP-governance tracking into the standardized rejection pipeline for unified active defense.
- Enhanced Handshake Observability: Captures `client` identifier and reports specific versioning and auth types at the `INFO` log level.

### Client Architecture & Orchestration
- Implemented a throttled `UpdateService` featuring a 6-hour rate-limit cooldown for GitHub discovery and state-gated listeners to minimize idle overhead.
- Introduced the `ProfileController` to decouple identity management and update tracking, adhering to the project's modularity "Principal Engineer" standards.
- Re-architected the Profile Hub into modular components: `UpdateCard` (atomic update feedback) and `ProfileInfoBlock` (identity visualization).
- Developed a Centralized Error Dispatcher in the `HomeScreen` for intelligent routing of protocol-level rejections (Bans, Updates, Auth failures).

### Performance, Stability & Logging
- Synchronized CID Logging: Captured assigned Connection IDs from the handshake to enable matched telemetry between client and server.
- Fixed a regression in `wsIdleTimeout` that caused aggressive reconnection cycles during background inactivity.
- Optimized UI notification responsiveness by refining SnackBar durations and pulse animation thresholds.
- Updated project documentation and README files across all stacks to reflect v2.20.0 security and functional enhancements.

---

## [2.19.0] - 2026-01-27
### Architectural & Structural Engineering
- Migrated to the "Smart" Modular Architecture, enforcing strict physical boundaries across five layers: Infrastructure (DI, Theme), Services (I/O, Domain Logic), Logic (Processors, Mappers), Controllers (Orchestration), and Feature-based UI.
- Decomposed the `WebSocketService` into an Orchestrator pattern, delegating specialized logic to independent sub-managers for Audio Buffering, Reconnection sequences, Heartbeat monitoring, and Reactive Configuration.
- Integrated an automated Session Lifecycle manager handling OIDC silent refresh flows and instant handshake re-synchronization upon identity changes.
- Refactored the `AuthService` into a modularized identity layer composed of an `OidcManager` (PKCE/OAuth2 protocol) and a `SessionManager` (Secure Token Persistence).
- Reorganized the feature-based UI hierarchy to isolate complex states (Recording, Settings, ProfileHub) into dedicated, testable domain folders.

### Security & Protocol Hardening
- Implemented the `HandshakePayloadBuilder` to standardize WebSocket metadata construction with tiered credential prioritization (OIDC > API Key).
- Hardened backend issuer validation utilizing slash-agnostic comparison to eliminate configuration mismatches between client and server.
- Refined URI normalization in the `TransportSecurityService` to strictly enforce WSS on public IPs while permitting explicit schemes for local development.
- Implemented a JavaScript-backed automated browser window closure verification for the OIDC callback flow.

### Backend Infrastructure & AI Performance
- Introduced predictive model warmup logic triggered immediately post-authentication to utilize user idle-time before recording starts.
- Implemented non-blocking model lifecycle management using threading locks and `asyncio.to_thread` to prevent event-loop starvation during GPU context loading.
- Optimized the backend execution environment via `uvloop` (C-based event loop) and `orjson` (high-speed binary serialization).
- Executed "Digital Liposuction" on the production Docker image, reducing size from 11.8GB to 7.35GB through static FFmpeg linking and aggressive layer pruning.
- Hardened memory hygiene using `malloc_trim` (via `ctypes`) to force OS-level RAM reclamation after Whisper model unloading.
- Implemented probabilistic silence gating to selectively return empty results when audio amplitudes fall below the noise floor, reducing transcription hallucination.

### Native Hardware Integration
- Developed the `AudioCueService` utilizing the native Windows `PlaySound` API for near-zero latency start/stop chimes.
- Implemented preloading of audio assets into native memory to bypass the overhead associated with standard high-level Dart audio packages.
- Added smart protocol detection to force `ws` on private/local network ranges, preempting TLS HandshakeErrors in local development environments.

---

## [2.13.0] - 2026-01-17
### Security Infrastructure & Identity
- Implemented RFC 7636 compliant PKCE (Proof Key for Code Exchange) authentication using the native system browser for secure identity tokens on Windows.
- Developed the `SecureVaultService`, leveraging Windows Credential Manager and PBKDF2 key derivation (100k iterations) seeded by the hardware Machine ID.
- Integrated a "Dual-Door" authentication engine supporting both stateless JWT validation (OIDC) and modular static API key verification.
- Enforced AES-256 field-level encryption for all transcription data persisted to the local Isar database using AES-CBC mode and hardware-bound IVs.
- Implemented JWKS (JSON Web Key Set) auto-discovery with a thread-safe, TTL-based public key caching layer to minimize authentication network overhead.

### Protocol Integrity & Active Defense
- Developed the "Handshake Cage" protocol, which enforces a valid JSON 'hello' sequence as the first message, buffering all incoming audio data until identity is verified.
- Implemented a bi-directional "Lock-Step" handshake to ensure granular synchronization between client and server states before promoting a connection to a ready state.
- Integrated the `BanStateService` with regex-based 1008 close code parsing to extract ban durations and provide real-time UI countdown streams.
- Hardened the transport layer with RFC 1918 validation to strictly block unencrypted WebSocket connections on public network interfaces.
- Implemented protocol algorithm pinning (RS256) and constant-time digest verification for static keys to mitigate substitution and timing side-channel attacks.

### UI Orchestration & Performance
- Refactored the `ActionBar` into a functional 5-button layout with a central dynamic connection security lock.
- Developed a multi-state security indicator system for real-time visualization of TLS 1.3/WSS, unencrypted local, and blocked/banned states.
- Optimized the desktop rendering engine by replacing global `SingleChildScrollView` structures with fixed-column layouts and internal text area scrolling to prevent UI jitter.
- Integrated high-resolution security thresholds and automated JWT expiry warning systems into the feature-layer configuration.

---

## [1.14.0] - 2026-01-12
### Core Automation & Win32 Integration
- Implemented direct Win32 clipboard API integration (`GlobalAlloc`, `SetClipboardData`) to achieve sub-150ms transcription-to-paste latency.
- Developed a native `GetMessage` blocking loop within a dedicated hardware isolate for global hotkey management, replacing resource-intensive timer polling.
- Migrated keyboard simulation from virtual keys to hardware scan codes to eliminate conflicts with the Flutter `HardwareKeyboard` internal state.
- Implemented foreground window detection logic to prevent recursive paste simulation when the application itself has focus.
- Introduced an "Immutable Isolate" pattern for hardware listeners, ensuring state purity through controlled isolate destruction and respawning.

### WebSocket Protocol & Connectivity
- Established a versioned WebSocket handshake protocol for robust client-server identification and feature capability negotiation.
- Implemented session-based lazy connections and a 5-minute automated idle timeout for efficient resource utilization.
- Developed an exponential backoff strategy for reconnections (scaling intervals up to 30 seconds) with integrated status synchronization.
- Standardized typed JSON error payloads (e.g., `NO_AUDIO`, `MODEL_LOADING`) to enable resilient UI-level exception handling.

### System Infrastructure & Build Engineering
- Implemented a multi-stage Docker build strategy (builder/runner pattern) to minimize the production footprint and secure build-time artifacts.
- Developed a comprehensive unit testing suite using `mocktail`, validating core service logic for Buffer limits, Incognito logic, and Isolate stability.
- Integrated a circular log buffer (200-entry capacity) with real-time stream emission for the in-app terminal-grade viewer.
- Implemented "Incognito Mode" (Ghost Mode) at the controller level to purge sensitive buffers and prevent persistent history logging during private sessions.
- Standardized the x64-exclusive Windows deployment pipeline via Inno Setup, including PE metadata rebranding for native Task Manager identification.
