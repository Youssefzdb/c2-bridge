#!/usr/bin/env python3
"""
SAA Chat — Interactive chat with the Sandbox Agent
Run it, talk to the agent, it can execute commands for you.

Usage:
  python3 chat.py                          # Default model (7B - fast)
  python3 chat.py --model qwen2.5-coder:32b # Big model (slower but smarter)
  python3 chat.py --no-exec                 # Chat only, no command execution
"""

import requests
import json
import sys
import os
import re
import subprocess
import argparse
import time

OLLAMA_URL = "http://localhost:11434"

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════

CHAT_SYSTEM = """You are SAA (Sandbox Autonomous Agent), running inside a Linux sandbox.
You are a helpful, capable AI assistant that can also execute commands.

When the user asks you to do something that requires running a command, wrap it in an action block:
```action
<command>
```

When you just want to chat or explain something, respond normally without an action block.

Rules:
- One action block per message max
- Keep responses concise and direct
- You speak Arabic, French, and English fluently
- You're a cybersecurity expert — pentesting, recon, vulnerability analysis
- Be casual and friendly, not robotic
"""

# Colors
C = {
    'R': '\033[91m', 'G': '\033[92m', 'Y': '\033[93m',
    'B': '\033[94m', 'C': '\033[96m', 'W': '\033[0m',
    'D': '\033[2m', 'BOLD': '\033[1m', 'M': '\033[95m'
}

def banner():
    print(f"""{C['C']}{C['BOLD']}
╔═══════════════════════════════════════════════╗
║   🤖 SAA Chat — Sandbox Agent Conversation  ║
╠═══════════════════════════════════════════════╣
║  Commands: /exit /clear /model /help /history║
║  Agent can execute commands — just ask!       ║
╚═══════════════════════════════════════════════╝{C['W']}
""")

def call_ollama(model, messages, stream=True):
    """Call Ollama with streaming response"""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": stream,
                "options": {
                    "temperature": 0.7,
                    "num_ctx": 8192,
                }
            },
            stream=stream,
            timeout=300
        )
        if resp.status_code != 200:
            print(f"{C['R']}Error: {resp.status_code} {resp.text[:100]}{C['W']}")
            return None
        
        if stream:
            full = ""
            for line in resp.iter_lines():
                if line:
                    chunk = json.loads(line)
                    text = chunk.get("message", {}).get("content", "")
                    if text:
                        full += text
                        print(text, end="", flush=True)
                    if chunk.get("done"):
                        break
            print()
            return full
        else:
            return resp.json().get("message", {}).get("content", "")
    except requests.exceptions.ConnectionError:
        print(f"{C['R']}Cannot connect to Ollama. Is it running?{C['W']}")
        return None
    except Exception as e:
        print(f"{C['R']}Error: {e}{C['W']}")
        return None

def execute_action(command):
    """Execute a command from an action block"""
    print(f"\n{C['Y']}⚡ Executing:{C['W']} {command[:150]}")
    try:
        proc = subprocess.Popen(
            command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=os.getcwd()
        )
        try:
            output, _ = proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
            output = proc.stdout.read() or ""
            output += "\n[TIMEOUT: 120s]"
        
        if len(output) > 4000:
            output = output[:4000] + "\n... [truncated]"
        
        print(f"{C['D']}{output}{C['W']}")
        return output.strip()
    except Exception as e:
        err = f"Error: {e}"
        print(f"{C['R']}{err}{C['W']}")
        return err

def parse_action(response):
    """Extract action block from response"""
    match = re.search(r'```action\s*(.*?)\s*```', response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def list_models():
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            return [m["name"] for m in resp.json().get("models", [])]
    except:
        pass
    return []

def main():
    parser = argparse.ArgumentParser(description="SAA Chat")
    parser.add_argument("--model", "-m", default="qwen2.5-coder:7b",
                       help="Ollama model to use")
    parser.add_argument("--no-exec", action="store_true",
                       help="Chat only, don't execute commands")
    args = parser.parse_args()

    # Check Ollama
    try:
        r = requests.get(f"{OLLAMA_URL}/api/version", timeout=5)
        if r.status_code != 200:
            print(f"{C['R']}Ollama not responding{C['W']}")
            sys.exit(1)
    except:
        print(f"{C['R']}Cannot reach Ollama at {OLLAMA_URL}{C['W']}")
        print(f"Start it: {C['Y']}LD_LIBRARY_PATH=/usr/local/lib/ollama ollama serve{C['W']}")
        sys.exit(1)

    model = args.model
    banner()
    
    available = list_models()
    if available:
        print(f"{C['D']}Available models: {', '.join(available)}{C['W']}")
    print(f"{C['C']}Using: {model}{C['W']}")
    if not args.no_exec:
        print(f"{C['G']}Command execution: ENABLED{C['W']}")
    else:
        print(f"{C['Y']}Command execution: DISABLED{C['W']}")
    print(f"{C['D']}Type /help for commands, /exit to quit{C['W']}\n")

    # Conversation history
    messages = [{"role": "system", "content": CHAT_SYSTEM}]
    
    while True:
        try:
            user_input = input(f"{C['G']}You> {C['W']}")
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C['Y']}Bye!{C['W']}")
            break

        if not user_input.strip():
            continue

        # Slash commands
        if user_input.startswith("/"):
            cmd = user_input.lower().strip()
            if cmd in ("/exit", "/quit"):
                print(f"{C['Y']}Bye!{C['W']}")
                break
            elif cmd == "/clear":
                messages = [{"role": "system", "content": CHAT_SYSTEM}]
                print(f"{C['Y']}Conversation cleared.{C['W']}\n")
                continue
            elif cmd == "/help":
                print(f"""{C['C']}
Commands:
  /exit     — Quit chat
  /clear    — Clear conversation history  
  /model    — List available models
  /history  — Show message count
  /help     — This message

Tips:
  Ask the agent to run commands: "scan localhost with nmap"
  Ask questions: "how do I exploit SQL injection?"
  Switch models: restart with --model qwen2.5-coder:32b
{C['W']}""")
                continue
            elif cmd == "/model":
                models = list_models()
                if models:
                    print(f"{C['C']}Models:{C['W']}")
                    for m in models:
                        marker = " ← current" if m == model else ""
                        print(f"  {m}{marker}")
                else:
                    print(f"{C['R']}No models found{C['W']}")
                continue
            elif cmd == "/history":
                print(f"{C['C']}Messages in context: {len(messages)}{C['W']}")
                continue
            else:
                print(f"{C['R']}Unknown command: {user_input}{C['W']}")
                continue

        # Add user message
        messages.append({"role": "user", "content": user_input})

        # Trim history if too long
        if len(messages) > 30:
            messages = [messages[0]] + messages[-28:]

        # Call agent
        print(f"{C['M']}🤖 {C['W']}", end="", flush=True)
        response = call_ollama(model, messages, stream=True)

        if response is None:
            messages.pop()
            continue

        # Add to history
        messages.append({"role": "assistant", "content": response})

        # Check for action block (command execution)
        if not args.no_exec:
            action = parse_action(response)
            if action:
                output = execute_action(action)
                # Feed output back to agent for a follow-up
                messages.append({
                    "role": "user",
                    "content": f"Command output:\n```\n{output}\n```\nRespond briefly."
                })
                print(f"{C['M']}🤖 {C['W']}", end="", flush=True)
                followup = call_ollama(model, messages, stream=True)
                if followup:
                    messages.append({"role": "assistant", "content": followup})

        print()

if __name__ == "__main__":
    main()
