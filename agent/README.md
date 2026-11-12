# DevOps AI Local Agent — interactive PTY MVP

Supports Windows PowerShell via pywinpty/ConPTY and Linux, WSL, and macOS via POSIX PTY.

## Start on Windows 11
In PowerShell, from this folder:
```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\start-windows.ps1
```

## Start on Linux, WSL, or macOS
```bash
chmod +x start-unix.sh
./start-unix.sh
```

The agent binds only to `127.0.0.1:8765`. It prints a generated pairing token on first launch and stores it in `agent-token.txt`. Keep the token private.

Health check: `http://127.0.0.1:8765/health`

## WebSocket protocol
Connect to `ws://127.0.0.1:8765/terminal/ws?token=YOUR_TOKEN`.
Send JSON messages:
- `{"type":"input","data":"ls\r"}`
- `{"type":"resize","cols":120,"rows":35}`
- `{"type":"close"}`

The agent runs shell commands as the logged-in OS user. This is a powerful local shell, not a sandbox. Only pair trusted applications and do not expose this port publicly.

## Production limitation
A public HTTPS website cannot directly connect to a local `ws://` endpoint because of mixed-content and browser local-network restrictions. For production, implement an agent-initiated authenticated WSS connection to the FastAPI backend, plus device enrollment/revocation and user-scoped routing. Do not expose port 8765 to the internet.
