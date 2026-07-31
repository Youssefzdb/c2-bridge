#!/usr/bin/env python3
"""
SAA Chat — Kali side client
Full bidirectional chat with the sandbox Ollama agent via C2 bridge.

Usage:
  python3 kali_chat.py                        # Fast model (7B)
  python3 kali_chat.py --model qwen2.5-coder:32b  # Smart model (32B)
  python3 kali_chat.py --no-exec              # Chat only, no commands
"""

import requests
import json
import sys
import os
import time
import argparse
import threading

BRIDGE_URL = "https://elio-acd17217.base44.app/functions/c2Bridge"
TOKEN = "shadow-core-c2-bridge-2026"
CHAT_REMOTE = "/app/conversations/6a6884ff4bc0607c4866ab4f/chat.py"

C = {
    'R': '\033[91m', 'G': '\033[92m', 'Y': '\033[93m',
    'C': '\033[96m', 'M': '\033[95m', 'W': '\033[0m', 'D': '\033[2m'
}

def api(method, data=None, params=None):
    url = BRIDGE_URL + "?token=" + TOKEN
    if params:
        for k, v in params.items():
            url += f"&{k}={v}"
    cmd = ["curl", "-s", "-m", "15", "-X", method, "-H", "Content-Type: application/json"]
    if method != "GET" and data:
        cmd.extend(["-d", json.dumps({**data, "token": TOKEN})])
    cmd.append(url)
    import subprocess
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if result.returncode == 0:
        return json.loads(result.stdout)
    return {"error": result.stderr}

def main():
    parser = argparse.ArgumentParser(description="SAA Chat — Kali Client")
    parser.add_argument("--model", "-m", default="qwen2.5-coder:7b")
    parser.add_argument("--no-exec", action="store_true")
    args = parser.parse_args()

    print(f"""{C['C']}
╔═══════════════════════════════════════════════════╗
║  SAA Chat — Kali → Sandbox Agent Connection     ║
╠═══════════════════════════════════════════════════╣{C['W']}
║  Model: {args.model:<42} ║
║  Exec:  {'ENABLED' if not args.no_exec else 'DISABLED':<42} ║
║  Bridge: C2 relay (bidirectional)                 ║
╚═══════════════════════════════════════════════════╝
""")
    
    # Check if there's an existing PTY session
    print(f"{C['D']}Checking for existing session...{C['W']}")
    
    # Start chat in sandbox via C2 (PTY mode for interactive)
    exec_flag = "--no-exec" if args.no_exec else ""
    remote_cmd = f"python3 {CHAT_REMOTE} --model {args.model} {exec_flag}"
    
    print(f"{C['D']}Starting chat session in sandbox...{C['W']}")
    result = api("POST", {"command": f"PTY:{remote_cmd}"})
    
    cmd_id = result.get("id", "")
    if not cmd_id:
        print(f"{C['R']}Failed to start session: {result}{C['W']}")
        sys.exit(1)
    
    print(f"{C['G']}Session started (ID: {cmd_id}){C['W']}")
    print(f"{C['D']}Waiting for agent to boot up...{C['W']}\n")
    
    # Poll for output
    last_len = 0
    input_ready = False
    input_buffer = ""
    
    def input_thread():
        nonlocal input_buffer, input_ready
        while True:
            try:
                line = input()
                input_buffer += line + "\n"
                input_ready = True
            except:
                break
    
    # Start input thread (only works in interactive terminal)
    try:
        t = threading.Thread(target=input_thread, daemon=True)
        t.start()
    except:
        pass
    
    while True:
        try:
            # Get output
            result = api("GET", params={"id": cmd_id})
            output = result.get("output", "")
            status = result.get("status", "")
            
            # Print new output
            if len(output) > last_len:
                new = output[last_len:]
                sys.stdout.write(new)
                sys.stdout.flush()
                last_len = len(output)
            
            # Send input if available
            if input_ready and input_buffer:
                api("PATCH", {"id": cmd_id, "input": input_buffer})
                input_buffer = ""
                input_ready = False
            
            if status in ("completed", "error"):
                break
            
            time.sleep(0.3)
        except KeyboardInterrupt:
            print(f"\n{C['Y']}Disconnecting...{C['W']}")
            api("PUT", {"id": cmd_id, "output": "Disconnected", "status": "completed"})
            break
        except Exception as e:
            print(f"{C['R']}Error: {e}{C['W']}")
            time.sleep(1)
    
    print(f"\n{C['Y']}Session ended.{C['W']}")

if __name__ == "__main__":
    main()
