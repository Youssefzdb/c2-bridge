# C2 Bridge — Real-Time Remote Shell

> Stream commands to a remote sandbox with **zero timeout** and **live output streaming**.

## What is this?

C2 Bridge is a lightweight command-and-control framework that lets you execute commands on a remote Base44 sandbox from your local machine (Kali Linux, or any OS with Python3). Unlike traditional SSH or reverse shells, C2 Bridge uses an HTTP-based relay (backend function) that:

- **Never times out** — commands can run for minutes (tested up to 60s+, no timeout)
- **Streams output in real-time** — you see output line-by-line as it's produced
- **Bypasses firewalls/NAT** — all communication is over HTTPS
- **Works behind proxies** — no direct connection needed between machines

## Architecture

```
┌─────────────┐         ┌─────────────────┐         ┌──────────────┐
│  Kali Linux │ ──HTTPS──│  c2Bridge API  │ ──poll── │  c2_worker   │
│  kali_c2.py │         │  (Base44 func)  │         │  (sandbox)   │
│             │ <─stream─│                 │ <─output─│              │
└─────────────┘         └─────────────────┘         └──────────────┘
```

1. **Kali** sends a command via POST to the c2Bridge API
2. **c2Bridge** stores the command in a database (Command entity)
3. **c2_worker.py** (running in sandbox) polls the bridge every 1 second
4. Worker executes the command and streams output back to the bridge
5. **Kali** polls the bridge and displays output in real-time (400ms polling)

## Files

| File | Where | Purpose |
|------|-------|---------|
| `kali_c2.py` | Your local machine | Interactive shell client |
| `c2_worker.py` | Remote sandbox | Background worker that executes commands |
| `c2_bridge.ts` | Base44 backend function | HTTP relay API |

## Quick Start

### On your Kali machine

```bash
# 1. Clone the repo
git clone https://github.com/Youssefzdb/c2-bridge.git
cd c2-bridge

# 2. Install dependencies
pip3 install requests

# 3. Make sure the sandbox worker is running
#    Tell your agent: "شغل الـ worker"

# 4. Launch the shell
python3 kali_c2.py
```

### Usage

```
╔══════════════════════════════════════════════════════╗
║          C2 STREAMING SHELL → Base44 Sandbox          ║
╠════════════════════════════════════════════════════════╣
║  Bridge: https://elio-acd17217.base44.app/...        ║
║  Poll:   400ms                                       ║
║  Mode:   Streaming (near real-time)                   ║
╚════════════════════════════════════════════════════════╝

[+] Sandbox worker: ONLINE
[+] Ready! Type commands below.
    exit/quit | clear | status | help

sandbox@c2:~$ whoami
root
sandbox@c2:~$ uname -a
Linux modal 4.19.0-gvisor x86_64 GNU/Linux
sandbox@c2:~$ nmap --version
Nmap version 7.94SVN ...
sandbox@c2:~$ exit
```

### Built-in Commands

| Command | Description |
|---------|-------------|
| `exit` / `quit` | Disconnect from the shell |
| `clear` | Clear the terminal screen |
| `status` | Check if the sandbox worker is online |
| `help` | Show help message |

Any other command is executed on the sandbox as a bash command.

## Configuration

Edit the config section at the top of `kali_c2.py`:

```python
BRIDGE_URL = "https://elio-acd17217.base44.app/functions/c2Bridge"
TOKEN = "shadow-core-c2-bridge-2026"
POLL_INTERVAL = 0.4  # 400ms for near-real-time
```

You can also pass the bridge URL as an argument:

```bash
python3 kali_c2.py --url https://your-bridge-url.base44.app/functions/c2Bridge
```

## Features

- ✅ **No timeout** — commands run until completion (tested 60s+)
- ✅ **Real-time streaming** — output appears line-by-line
- ✅ **Interactive spinner** — visual feedback for long commands
- ✅ **Worker status check** — know if the sandbox is online before sending
- ✅ **Cloudflare bypass** — uses curl-based HTTP to avoid bot detection
- ✅ **Auto-retry** — worker reconnects automatically on errors

## Security Notes

- The bridge uses a shared token for authentication
- All communication is over HTTPS
- The sandbox worker runs as root (sandbox environment)
- Do NOT use this for unauthorized access — only on systems you own/control

## Testing

### Test streaming
```bash
sandbox@c2:~$ for i in 1 2 3 4 5; do echo "Line $i"; sleep 1; done
```

### Test long-running command (30s)
```bash
sandbox@c2:~$ echo START && sleep 10 && echo 10s && sleep 10 && echo 20s && sleep 10 && echo DONE
```

## License

MIT — Use freely for authorized security testing and research.

## Author

**Youssef Zaidi** — Penetration Tester & Offensive Security Specialist  
GitHub: [@Youssefzdb](https://github.com/Youssefzdb)
