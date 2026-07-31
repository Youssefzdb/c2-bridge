#!/usr/bin/env python3
"""
SAA Chat v2 — Non-interactive (works through C2 bridge / GitHub relay)
Takes a message as argument, talks to Ollama, executes commands, returns response.

Usage (from kali_shell or direct):
  python3 chat_agent.py "hello, who are you?"
  python3 chat_agent.py "scan example.com with nmap"
  python3 chat_agent.py --model qwen2.5-coder:32b "analyze this target"

History is saved to chat_history.json for multi-turn conversation.
"""

import requests
import json
import sys
import os
import re
import subprocess
import argparse

OLLAMA_URL = "http://localhost:11434"
HISTORY_FILE = "chat_history.json"
MAX_HISTORY = 20  # Keep last 20 messages

CHAT_SYSTEM = """You are SAA (Sandbox Autonomous Agent), running inside a Linux sandbox.
You are a helpful, capable AI assistant that can also execute commands.

When the user asks you to do something that requires running a command, wrap it in an action block:
```action
<command>
```

When you just want to chat or explain something, respond normally without an action block.

Rules:
- One action block per message max
- Keep responses concise and direct (max 200 words unless asked for detail)
- You speak Arabic, French, and English fluently
- You're a cybersecurity expert — pentesting, recon, vulnerability analysis
- Be casual and friendly, not robotic
- If you run a command, briefly explain what you found
"""

def load_history():
    """Load conversation history from file"""
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except:
        return [{"role": "system", "content": CHAT_SYSTEM}]

def save_history(messages):
    """Save conversation history to file"""
    # Keep system message + last MAX_HISTORY messages
    trimmed = [messages[0]] + messages[-MAX_HISTORY:]
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(trimmed, f, indent=2)
    except:
        pass

def call_ollama(model, messages):
    """Call Ollama (non-streaming, returns full response)"""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_ctx": 8192,
                }
            },
            timeout=300
        )
        if resp.status_code != 200:
            return f"[Error: Ollama returned {resp.status_code}]"
        return resp.json().get("message", {}).get("content", "")
    except requests.exceptions.ConnectionError:
        return "[Error: Cannot connect to Ollama. Run: LD_LIBRARY_PATH=/usr/local/lib/ollama ollama serve]"
    except Exception as e:
        return f"[Error: {e}]"

def execute_action(command):
    """Execute a command from an action block"""
    try:
        proc = subprocess.Popen(
            command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True, cwd=os.getcwd()
        )
        try:
            output, _ = proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            output = "[TIMEOUT: 120s]"
        
        if len(output) > 5000:
            output = output[:5000] + "\n... [truncated]"
        
        return output.strip()
    except Exception as e:
        return f"Error: {e}"

def parse_action(response):
    """Extract action block from response"""
    match = re.search(r'```action\s*(.*?)\s*```', response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def main():
    parser = argparse.ArgumentParser(description="SAA Chat Agent (non-interactive)")
    parser.add_argument("message", nargs="?", default="", help="Message to send to agent")
    parser.add_argument("--model", "-m", default="qwen2.5-coder:7b", help="Ollama model")
    parser.add_argument("--no-exec", action="store_true", help="Don't execute commands")
    parser.add_argument("--clear", action="store_true", help="Clear conversation history")
    parser.add_argument("--history", action="store_true", help="Show conversation history")
    args = parser.parse_args()

    # Clear history
    if args.clear:
        try:
            os.remove(HISTORY_FILE)
            print("[History cleared]")
        except:
            print("[No history file]")
        return

    # Show history
    if args.history:
        msgs = load_history()
        for m in msgs:
            role = m["role"]
            content = m["content"][:200]
            print(f"[{role}] {content}...")
        return

    # Check Ollama
    try:
        r = requests.get(f"{OLLAMA_URL}/api/version", timeout=5)
        if r.status_code != 200:
            print("[Error: Ollama not responding. Run: ollama serve]")
            return
    except:
        print("[Error: Cannot reach Ollama at localhost:11434]")
        print("[Start it: LD_LIBRARY_PATH=/usr/local/lib/ollama ollama serve]")
        return

    if not args.message:
        # Read from stdin if available
        if not sys.stdin.isatty():
            args.message = sys.stdin.read().strip()
        if not args.message:
            print("Usage: python3 chat_agent.py \"your message here\"")
            print("       python3 chat_agent.py --model qwen2.5-coder:32b \"complex question\"")
            print("       python3 chat_agent.py --clear  (reset conversation)")
            return

    # Load conversation history
    messages = load_history()
    
    # Add user message
    messages.append({"role": "user", "content": args.message})

    # Call Ollama
    response = call_ollama(args.model, messages)
    
    if response.startswith("[Error:"):
        print(response)
        return

    # Add response to history
    messages.append({"role": "assistant", "content": response})

    # Check for action block (command execution)
    if not args.no_exec:
        action = parse_action(response)
        if action:
            print(f"\n⚡ Executing: {action}")
            output = execute_action(action)
            print(f"Output:\n{output}")
            
            # Feed output back to agent for follow-up
            messages.append({
                "role": "user",
                "content": f"Command output:\n```\n{output}\n```\nRespond briefly with what you found."
            })
            followup = call_ollama(args.model, messages)
            if not followup.startswith("[Error:"):
                messages.append({"role": "assistant", "content": followup})
                print(f"\n🤖 {followup}")
        else:
            print(f"\n🤖 {response}")
    else:
        print(f"\n🤖 {response}")

    # Save history
    save_history(messages)

if __name__ == "__main__":
    main()
