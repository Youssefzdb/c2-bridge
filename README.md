# C2 Bridge — Real-time Command & Control

Autonomous AI agent platform that bridges a local Kali Linux machine with a cloud sandbox via a serverless C2 relay. Includes an Ollama-powered autonomous agent that can execute commands, iterate, and complete tasks independently.

## Architecture

```
┌─────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Kali Linux │ ◄────► │  Base44 Backend   │ ◄────► │   Sandbox       │
│   (Attacker) │  HTTP  │  (C2 Bridge API)  │  HTTP  │   (Worker +     │
│              │        │  Entity Queue     │        │   Ollama Agent) │
└─────────────┘         └──────────────────┘         └─────────────────┘
```

## Components

### C2 Bridge
| File | Description |
|------|-------------|
| `c2_bridge.ts` | Serverless backend function — command queue via entity storage |
| `c2_worker_v7.py` | Bulletproof sandbox worker — polls bridge, executes commands, returns output |
| `c2_stream_shell.py` | Real-time reverse shell from sandbox to Kali (PTY, auto-reconnect, SSL) |
| `kali_c2.py` | Kali-side C2 client — sends commands, receives streaming output |

### AI Agent (Ollama-powered)
| File | Description |
|------|-------------|
| `agent.py` | **Sandbox Autonomous Agent (SAA)** — self-directed AI agent that loops, decides, and executes commands |
| `chat.py` | Interactive chat with the agent in the sandbox |
| `kali_chat.py` | Kali-side chat client — talks to sandbox agent via C2 bridge |
| `kali_chat.sh` | Bash version of the Kali chat client |

## Setup

### 1. Backend (Base44 Sandbox)
```bash
# Start Ollama with models
ollama serve &
ollama pull qwen2.5-coder:7b   # Fast mode
ollama pull qwen2.5-coder:32b  # Smart mode

# Start C2 worker (bulletproof, auto-restart)
nohup python3 c2_worker_v7.py &

# Optional: Start the autonomous agent
python3 agent.py "Scan 10.10.10.1 for open ports and report findings"

# Optional: Interactive chat
python3 chat.py --model qwen2.5-coder:7b
```

### 2. Kali Linux (Attacker)
```bash
# Clone
git clone https://github.com/Youssefzdb/c2-bridge.git
cd c2-bridge

# Interactive C2 shell
python3 kali_c2.py

# Chat with sandbox agent
python3 kali_chat.py

# Or use bash version
bash kali_chat.sh
```

## C2 Worker v7 Features

- **Recursion guard** — blocks `kali_*` scripts from running in sandbox (prevents deadlock)
- **30s timeout** — any command that hangs gets killed
- **`stdin=DEVNULL`** — commands waiting for input won't block the worker
- **Auto-restart** — crashes automatically recover
- **400ms polling** — near real-time command pickup

## SAA Agent Features

- **Autonomous loop** — executes commands, analyzes output, iterates until task is complete
- **Multi-language** — speaks Arabic, French, English
- **Cybersecurity expert** — pentesting, recon, vulnerability analysis
- **Interactive & task modes** — `agent.py "task"` or `agent.py --interactive`
- **Two models** — 7B (fast, 3 tok/s) or 32B (smart, 1.6 tok/s)

## Usage Examples

### C2 Shell (Kali → Sandbox)
```bash
sandbox@c2:~$ nmap -sS 10.10.10.1
sandbox@c2:~$ python3 fasset_recon.py
sandbox@c2:~$ curl -s https://target.com | head -50
```

### Autonomous Agent (Sandbox)
```bash
python3 agent.py "Find all subdomains of example.com using crt.sh"
python3 agent.py "Scan 10.10.10.1 for open ports and identify services"
python3 agent.py "Build a Python port scanner and test it on localhost"
```

### Chat (Interactive)
```bash
python3 chat.py
You> what services are running on this machine?
🤖 [executes ss -tlnp and responds with analysis]
```

## Security

- C2 bridge requires authentication token
- Worker blocks recursive commands
- All communication over HTTPS
- Optional SSL for reverse shell

## Author

**Youssef Zaidi** — Cybersecurity Specialist (Penetration Testing & Offensive Security)
- GitHub: [@Youssefzdb](https://github.com/Youssefzdb)
