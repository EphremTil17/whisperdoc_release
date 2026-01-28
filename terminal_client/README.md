# WhisperDoc Client (v2.19.0) - High-Performance Handshake

A secure, modular, and high-performance Python terminal client for real-time dictation using the optimized WhisperDoc v2.14.0 backend.

## Features

### Enterprise-Grade Security
*   **Secure API Key Storage (OS Enclave)**: Uses the native OS credential manager via `keyring` (Windows Credential Manager, macOS Keychain, Linux Secret Service). Keys are **never** persisted in plain text files.
*   **Zero-Trust Fail-Secure Architecture**: Validates credentials against the server *before* initializing hardware. If authentication fails, the client terminates immediately without exposing microphone access.
*   **Transport Security & RFC 1918 Compliance**: Enforces `wss://` (TLS 1.2+) for all remote connections. Intelligently falls back to plain text (`ws://`) **only** if the target is a verified private network IP (e.g., `192.168.x.x`).
*   **Incognito Mode (Ghost Mode)**: A protocol-level privacy state enforcing zero-persistence on the backend. When enabled, privacy is negotiated during the initial handshake, triggering server-side log redaction.

### Performance & UX
*   **Global Hotkeys & Single Instance**: Control recording (Default: `Ctrl+Alt+W`) system-wide. Uses a Windows Mutex to ensure only one instance runs at a time (preventing mic conflicts).
*   **Active Defense Awareness**: Intelligently handles `1008` (Policy Violation) closures. The client respects server-mandated "Cooldown" periods and provides clear user feedback on ban status.
*   **Hardened Handshake Protocol**: Implements strict authentication sequencing. Audio data is only transmitted after the identity-verified handshake is successfully acknowledged by the backend.
*   **Low-Latency PCM Streaming**: Streams raw PCM audio chunks in real-time with zero-latency handover.
*   **Smart Auto-Paste**: Automatically types transcriptions into your active cursor instantly upon processing completion.

## Getting Started

### 1. Prerequisites
- **Python 3.8+**
- **PortAudio**: Usually included with pip wheels.
  - *Linux*: `sudo apt install libportaudio2`

### 2. Installation - Linux/Windows/MacOS

After making sure you are in the client dir:
```bash
cd client
```
Create a virtual environment and install dependencies:
```bash
python -m venv venv

# Windows
.\venv\Scripts\Activate.ps1
# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Launch & Configuration
Simply start the client. If it’s your first time, the interactive wizard will guide you through server setup and microphone selection:
```bash
python whisper_client.py
# or
python whisper_client.py --setup
```
*   **API Key**: You will be prompted for your API Key, which is then stored securely in your OS Enclave.
*   **Hardware**: Select your microphone device and hotkey during prompts.
*   **Ready**: Once you see "Client Ready", press (Default: **Ctrl+Alt+W**) to start dictating.

## CLI Options

| Flag | Description |
| :--- | :--- |
| `--setup` | Re-run the interactive setup wizard (Mic/Host selection). |
| `--clear-key` | Wipe the stored API key from the OS keyring. |
| `--incognito` | Enable Ghost Mode (No server logs, redacted output). |
| `--health` | Perform a pre-flight health check on the backend. |
| `--version` | Display current client version. |

**Example:**
```bash
# Force re-configure audio device
python whisper_client.py --setup
```

## Troubleshooting

*   **Manual Edits**: If you prefer manual configuration, you can edit the `.env` file created after the first run.
*   **Auth Reset**: If the server rejects your key, use `--clear-key` to reset it.
*   **Linux/Wayland**: Global hotkeys may require X11 or specific compositor permissions.
