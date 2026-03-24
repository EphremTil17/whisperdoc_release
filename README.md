# WhisperDoc v2.23.6 (Public Release)

### NOT SOURCE CODE - For Public Release Only

<img width="3375" height="3363" alt="WhisperDoc Github Preview" src="https://github.com/user-attachments/assets/661f6737-b885-4d5d-b2a7-91ce8392a0de" />

##
A high-performance, **multi-layered secure**, and production-ready speech-to-text system featuring a **pluggable multi-engine ASR architecture** (OpenAI Whisper, NVIDIA Parakeet) with GPU acceleration within a **hardened, read-only enclosure**, paired with modern, zero-trust client applications for seamless, identity-verified dictation.


https://github.com/user-attachments/assets/a6034fd9-7f4b-4279-9e5b-acfc6238f626


## Purpose

WhisperDoc Client provides a lightweight, always-ready interface for voice dictation. It captures audio from your microphone, streams it to a self-hosted or public WhisperDoc backend server, and receives transcriptions in real-time. The transcribed text can be automatically copied to your clipboard and pasted into any application.

This client is designed for users who need fast, accurate dictation without leaving their current workflow. Press a global hotkey, speak, and your words appear wherever your cursor is.

## Downloads

Pre-built Windows installers are available in the [win_x64_release/](win_x64_release/) directory. Download the latest `.exe` and run the installer.

### Prerequisites

- Windows 10/11 (x64)
- A running WhisperDoc backend server — you can self-host with Docker and an NVIDIA GPU, or connect to the public demo server at **`https://whisper.ephremst.com`** to try it out immediately

## Security & Protocol Infrastructure

Both clients share a hardened security and transport foundation, enforcing enterprise-grade zero-trust principles end-to-end:

- **Credential Isolation**: API keys and identity tokens are stored exclusively in the **Windows Credential Manager** (OS Enclave). Sensitive credentials are never written to plain-text configuration files or persisted to disk unprotected.
- **Handshake Cage Protocol**: A strict WebSocket state machine that buffers audio locally and only flushes to the socket *after* the identity-verified handshake is acknowledged by the backend. The server is hardened to immediately drop and blacklist IPs that attempt to stream audio before successful identity verification. No data leaves the client until the connection is fully authenticated.
- **Transport Security & RFC 1918**: Mandatory `wss://` (TLS 1.2+) is enforced for all public connections. Plain-text `ws://` is permitted **only** after validating the target as a verified local private network IP (RFC 1918).
- **Structured Error Protocol**: All WebSocket error payloads include both a numeric `code` (for backwards compatibility) and a structured `error_code` string (e.g., `AUTH_FAILED`, `VERSION_OUTDATED`, `IP_BANNED`) for precise client-side error routing. Both clients route all 12 backend error types with user-specific guidance and actionable messages.
- **Active Defense Awareness**: Both clients intelligently handle `1008` (Policy Violation) closures and respect server-mandated ban cooldown periods, preventing reconnection storms against the backend's circuit breaker.
- **Incognito Mode (Ghost Mode)**: Protocol-level privacy flag that ensures zero-disk persistence on the backend, performs explicit RAM clearing of sensitive transcription buffers on the client, and redacts server-side logs so that sensitive transcriptions leave no trace in backend telemetry.
- **Auto Copy/Paste**: Transcriptions are automatically placed on the clipboard and pasted at the active cursor position, enabling seamless dictation into any application.

## Clients

### Flutter Client (Primary) — Windows v2.23.6

A high-performance Windows desktop application built with a **Smart Modular Architecture** designed for high scalability and zero-latency performance.

- **Instantaneous Connection**: Implements a "Zero-Latency" recording flow. Audio capture and UI feedback initiate instantly while the WebSocket handshake completes in parallel. The transport layer automatically resumes connectivity when a recording is initiated, removing the need for manual connection management.
- **Identity Federation (OIDC/PKCE)**: Implements industry-standard OAuth2 PKCE (Proof Key for Code Exchange) flow via the **System Browser**. Built with a custom Dart implementation for maximum transparency and Windows compatibility. The system enforces strict identity verification via **Asymmetrical RS256 signing** and has been verified to reject Algorithm Confusion attacks (HS256) and `none` algorithm bypass attempts.
- **Data-at-Rest Encryption**: Transcription history is stored in an **AES-256 encrypted Isar database**. Encryption keys are derived uniquely per-installation using hardware-bound salts and PBKDF2.
- **Native Win32 Integration**: Direct API calls for clipboard (`GlobalAlloc`, `SetClipboardData`) achieving sub-150ms transcription-to-paste latency. Native `GetMessage` blocking loop within a dedicated hardware isolate for global hotkey management — hotkeys work reliably after system sleep/hibernate. Single-instance enforcement via Win32 Named Mutex prevents resource contention on hotkeys and microphone handles.
- **Reconnection Intelligence**: Identity-state-driven reconnects that trigger on meaningful credential changes rather than every auth pulse, reducing reconnect churn around silent refresh. Exponential backoff strategy with integrated ban awareness.
- **Advanced Security Indicators**: Visual feedback (Lock/Warning/Block) for real-time visualization of TLS 1.3/WSS, unencrypted local, and blocked/banned connection states.
- **JWT Expiry Warnings**: Automatic detection of session tokens with user-friendly expiry countdowns. Profile-based logic prevents "Update Available" notifications during active transcription and immediately blocks usage when security patches are required.
- **Glassmorphic UI**: Modern, translucent design with Lexend typography and integrated OIDC identity hardening across configuration sub-menus.
- **Verification Suite**: Bundled modular security tests validating PKCE cryptographic integrity and state-parameter protection.

### Python Terminal Client — Windows Only v2.23.6

A secure, modular, and production-ready **Windows-only** terminal client built as a lightweight fallback/debug tool for when the Flutter app is unavailable. Managed via [uv](https://docs.astral.sh/uv/) with `pyproject.toml`, `uv.lock`, typed transport message boundaries, and full quality gates.

- **Keepalive Ping**: Maintains persistent connections through Cloudflare Tunnel and reverse proxy idle timeouts.
- **Exponential Backoff Reconnection**: Jittered retries with configurable max attempts (default 10), preventing thundering herd on backend restarts.
- **Granular Handshake State Machine**: Distinguishes between BANNED, VERSION_OUTDATED, and FAILED states with appropriate user messaging and recovery behavior.
- **Automated First-Time Setup**: Interactive guided configuration for server URI, API key, and preferences on first launch.
- **Pytest + Pyright + Ruff Quality Gates**: Full automated test coverage, static type checking, and lint/format enforcement via repo-wide pre-commit hooks.

> **Note**: The terminal client is explicitly scoped to Windows desktop use. Unsupported platforms (Linux/WSL) exit early with a clear operator-facing message instead of falling through to opaque `pynput`/X server errors.

## Backend Overview

The backend is a Dockerized FastAPI server with a **pluggable ASR engine layer** operating within a **read-only container runtime** for maximum enclosure security. The backend packages are managed via native [uv](https://docs.astral.sh/uv/) with `pyproject.toml` and `uv.lock` for reproducible, lockfile-driven builds.

### Core Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ASR_ENGINE` | ASR backend (`whisper` or `parakeet`) | `whisper` |
| `MODEL_NAME` | Whisper model (e.g., `tiny.en`, `large-v3-turbo`) | `large-v3-turbo` |
| `MODEL_DEVICE` | Hardware allocation (`cuda` or `cpu`) | `cuda` |
| `API_PORT` | Backend listening port | `9989` |
| `LOG_LEVEL` | Logging verbosity (DEBUG, INFO, SUCCESS) | `INFO` |

Engine switching is configuration-driven — set `ASR_ENGINE` in `.env` and rebuild. A single Docker service selects its Dockerfile via the engine variable, so switching engines is a configuration change followed by rebuild, not a service topology change.

### ASR Engine Benchmarks

Benchmarks from the [Open ASR Leaderboard](https://huggingface.co/spaces/hf-audio/open_asr_leaderboard) on standardized evaluation datasets:

| Engine | Model | WER (%) ↓ | RTFx ↑ | Language | VRAM (fp16) |
|--------|-------|-----------|--------|----------|-------------|
| **Parakeet** | `nvidia/parakeet-tdt-0.6b-v2` | **6.05** | **3,386** | English | ~2.4 GB |
| **Whisper** | `openai/whisper-large-v3-turbo` | 7.83 | 200 | Multilingual | ~3.5 GB |

- **WER** (Word Error Rate): Lower is better. Parakeet achieves 23% lower WER than Whisper Turbo.
- **RTFx** (Real-Time Factor): Higher is better. Parakeet is ~17x faster than Whisper Turbo due to its non-autoregressive TDT architecture.
- Both engines run in **float16** precision with negligible accuracy loss vs float32.

### Infrastructure & Performance

- **Model Loading**: First launch downloads the model. Subsequent starts are fast due to caching in `./model-cache`. Cache-first loading attempts `local_files_only=True` before hitting the network, eliminating avoidable HuggingFace revision checks on warm cache.
- **Transcription**: ~1s for a 10-second audio file on an RTX 3060TI.
- **GPU Acceleration**: CUDA-enabled using the `ctranslate2` engine (Whisper) or native PyTorch (Parakeet).
- **Dynamic VRAM Scaling**: Intelligent engine orchestration that unloads models from VRAM after periods of inactivity, with aggressive `malloc_trim` RAM reclamation to force OS-level heap memory recovery.
- **High-Performance I/O**: Integrated **uvloop** (C-based event loop) and **orjson** (sub-millisecond JSON serialization) to minimize I/O latency and CPU overhead during heavy concurrency.
- **Weight Efficiency**: Multi-stage Docker builds with static FFmpeg binaries and aggressive layer pruning, resulting in a ~40% reduction in production image footprint.

## Client Configuration

Access settings via the gear icon or hamburger menu in the Flutter client:

- **Server URI**: WebSocket endpoint (e.g., `wss://whisper.ephremst.com/ws` or `ws://localhost:9989/ws`)
- **Secure Key**: API Key or JWT (stored in Windows Credential Manager)
- **Global Hotkey**: Customize your trigger key combination (default: `Ctrl+Alt+E`)
- **Auto Copy/Paste**: Control automation behavior

## Release History

Detailed changelogs and per-version release notes are available in:

- [CHANGELOG.md](CHANGELOG.md) — Technical changelog across all versions
- [release_notes/](release_notes/) — Detailed per-version release notes

## License

See the root project LICENSE file.
