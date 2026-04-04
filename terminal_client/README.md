# WhisperDoc Terminal Client (v2.24.6)

A secure, modular Python terminal client for real-time dictation using the WhisperDoc backend. It is the supported Windows fallback and diagnostic client when the Flutter desktop app is unavailable or when you want lower-level visibility into transport behavior.

## Features

### Enterprise-Grade Security

- **Secure API Key Storage (OS Enclave)**: Uses the native OS credential manager via `keyring` and stores secrets in Windows Credential Manager. Keys are **never** persisted in plain text files.
- **Zero-Trust Fail-Secure Architecture**: Validates credentials against the server _before_ initializing hardware. If authentication fails, the client terminates immediately without exposing microphone access.
- **Transport Security & Identity Integrity**: Enforces strict certificate validation against the system **Root CA Store**. Validates hostnames for remote origins to prevent local "Man-in-the-Middle" (MITM) attacks.
- **Input Sanitization & Injection Shield**: Employs a whitelist-based sanitizer to strip malicious ANSI escape sequences and control characters from transcriptions before they touch the clipboard or terminal display.
- **Credential Memory Hygiene & OOM Protection**: API keys are scrubbed from process memory immediately after use. The audio buffer includes a strict safety cap to prevent memory exhaustion during long-running sessions.
- **Incognito Mode (Ghost Mode)**: A protocol-level privacy state enforcing zero-persistence on the backend. When enabled, privacy is negotiated during the initial handshake, triggering server-side log redaction.

### Performance & UX

- **Global Hotkeys & Single Instance**: Control recording (Default: `Ctrl+Alt+W`) system-wide. Uses a Windows Mutex to ensure only one instance runs at a time (preventing mic conflicts).
- **Structured Error Handling**: Parses all 12 backend `error_code` types (`AUTH_FAILED`, `IP_BANNED`, `VERSION_OUTDATED`, `MAX_CONNECTIONS`, etc.) and surfaces user-specific guidance for each — including key reset prompts, update notices, and capacity warnings.
- **Granular Handshake State Machine**: Five-state machine (`LOCKED`, `AUTHENTICATING`, `AUTHENTICATED`, `FAILED`, `BANNED`, `VERSION_OUTDATED`) with error context propagation to the UI layer.
- **Keepalive Ping**: Sends periodic pings every 45 seconds to prevent Cloudflare Tunnel idle connection drops (~100s threshold).
- **Exponential Backoff Reconnection**: Automatic reconnection with jittered exponential backoff (base 1s, max 60s, 10 attempts). Terminal states (banned, version outdated) and intentional disconnects suppress reconnection.
- **Hardened Handshake Protocol**: Implements strict authentication sequencing. Audio data is only transmitted after the identity-verified handshake is successfully acknowledged by the backend.
- **Low-Latency PCM Streaming**: Streams raw PCM audio chunks in real-time with zero-latency handover.
- **Instant-Ready Lifecycle**: Proactively authenticates and warms up the backend connection on client launch, ensuring the model is loaded before you even press the hotkey.
- **Zero-Loss Parallel Buffering**: Instantly captures and buffers audio even if the client is idle or reconnecting. Audio is flushed the moment the handshake completes, ensuring no lost words.
- **Resource-Efficient Idle Timeout**: Automatically disconnects after 5 minutes of inactivity (configurable) to free up backend GPU memory.
- **Smart Auto-Paste**: Automatically types transcriptions into your active cursor instantly upon processing completion.

### Modern Modular Architecture

- **Lego-Style Modularity**: Organized into strict **Logic**, **Services**, and **Controller** layers. Decoupled domain logic from terminal-specific handling.
- **Zero-Latency Pipeline**: Asynchronous orchestration allows parallel audio capture, buffering, and server handshaking.

## Getting Started

### 1. Supported Platform

- **Windows** with a desktop session
- **Python 3.10+**
- **uv**

This client is not a supported Linux/WSL runtime. It depends on Windows-native global hotkey and clipboard behavior.

### 2. Installation - Windows

After making sure you are in the terminal client dir:

```bash
cd terminal_client
```

Sync the project and install the dev tools:

```bash
uv sync --group dev
```

### 3. Launch & Configuration

Simply start the client. If it’s your first time, the interactive wizard will guide you through server setup and microphone selection:

```bash
uv run whisperdoc-terminal
# or
uv run whisperdoc-terminal --setup
```

You can also run the package module directly:

```bash
uv run python -m whisper_shell
```

- **API Key**: You will be prompted for your API Key, which is then stored securely in your OS Enclave.
- **Hardware Validation**: Select your microphone device and host API (e.g., **WASAPI**). The setup wizard strictly enforces valid hardware configurations to prevent "ghost" audio inputs.
- **Ready**: Once you see "Client Ready", press (Default: **Ctrl+Alt+W**) to start dictating.

`whisper_client.py` remains as a compatibility shim, but the UV commands above are the supported workflow.

## CLI Options

| Flag          | Description                                               |
| :------------ | :-------------------------------------------------------- |
| `--setup`     | Re-run the interactive setup wizard (Mic/Host selection). |
| `--clear-key` | Wipe the stored API key from the OS keyring.              |
| `--incognito` | Enable Ghost Mode (No server logs, redacted output).      |
| `--health`    | Perform a pre-flight health check on the backend.         |
| `--version`   | Display current client version.                           |

**Example:**

```bash
# Force re-configure audio device
uv run whisperdoc-terminal --setup
```

## Testing

The terminal client ships with a comprehensive pytest suite covering the handshake state machine, transport error routing, reconnection backoff, recording controller orchestration, payload builder, audio buffer, sanitizer, and CLI initialization.

```bash
cd terminal_client

# Lint and import ordering
uv run ruff check .

# Auto-fix safe lint issues
uv run ruff check . --fix

# Format the codebase
uv run ruff format .

# Run all tests with coverage
uv run pytest tests/ --cov=whisper_shell --cov-report=term-missing

# Run a specific test file
uv run pytest tests/test_handshake.py -v

# Run Pyright against the runtime package
uv run pyright
```

## Troubleshooting

- **Manual Edits**: If you prefer manual configuration, you can edit the `.env` file created after the first run.
- **Auth Reset**: If the server rejects your key, use `--clear-key` to reset it.
- **Unsupported Environment**: Linux/WSL launches are intentionally unsupported and now exit early with a clear message instead of falling through to GUI/X hotkey errors.
