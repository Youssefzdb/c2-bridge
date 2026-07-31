#!/usr/bin/env python3
"""
Kali Chat Client v2 — Send messages to SAA agent in the sandbox via GitHub relay.

This replaces the old interactive chat.py that needed stdin (which doesn't work
through the C2 bridge). Now it's simple: send a message, get the agent's response.

Usage:
  python3 kali_chat.py "hello, who are you?"
  python3 kali_chat.py "scan example.com with nmap"
  python3 kali_chat.py "find subdomains of target.com"
  python3 kali_chat.py --status   # check if agent is running

The agent runs autonomously — it will execute commands, iterate, and report back.
Conversation history persists between messages.

Requirements:
  pip install requests
  export GITHUB_TOKEN="gho_xxx"
"""

import requests
import json
import sys
import os
import base64
import time
import uuid
import argparse
from datetime import datetime

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_ACCESS_TOKEN", "")
REPO = "Youssefzdb/c2-bridge"
CHAT_QUEUE = "agent_chat.json"
CHAT_RESPONSE = "agent_response.json"
POLL_INTERVAL = 2
MAX_WAIT = 300  # 5 minutes max for response

# Colors
R = "\033[91m"
G = "\033[92m"
Y = "\033[93m"
C = "\033[96m"
B = "\033[1m"
D = "\033[2m"
W = "\033[0m"
M = "\033[95m"

def github_get_file(path):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    try:
        resp = requests.get(url, headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            sha = data["sha"]
            return content, sha
        return None, None
    except Exception as e:
        print(f"{R}  Error: {e}{W}")
        return None, None

def github_put_file(path, content, sha=None, message="Chat message"):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {"message": message, "content": encoded}
    if sha:
        payload["sha"] = sha
    try:
        resp = requests.put(url, headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }, json=payload, timeout=15)
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"{R}  Error: {e}{W}")
        return False

def send_message(msg):
    """Send a message to the agent via GitHub"""
    msg_id = str(uuid.uuid4())[:8]
    chat_data = {
        "id": msg_id,
        "message": msg,
        "timestamp": datetime.now().isoformat()
    }
    
    # Check if queue is busy (previous message not processed)
    existing, existing_sha = github_get_file(CHAT_QUEUE)
    if existing:
        print(f"{Y}  [!] Queue busy — waiting for agent to process previous message...{W}")
        for i in range(60):
            time.sleep(2)
            existing, existing_sha = github_get_file(CHAT_QUEUE)
            if not existing:
                break
            if i % 10 == 0:
                print(f"{D}  ...still waiting ({i*2}s){W}")
        if existing:
            print(f"{R}  [!] Queue still busy after 120s. Agent may be offline.{W}")
            return None
    
    # Write message to queue
    ok = github_put_file(CHAT_QUEUE, json.dumps(chat_data, indent=2),
                        sha=existing_sha,
                        message=f"Chat [{msg_id}]")
    if not ok:
        print(f"{R}  [ERROR] Failed to send message{W}")
        return None
    
    return msg_id

def get_response(msg_id, max_wait=MAX_WAIT):
    """Poll for agent response"""
    start = time.time()
    last_id = None
    
    print(f"{D}  Waiting for agent response...{W}", end="", flush=True)
    
    while time.time() - start < max_wait:
        content, _ = github_get_file(CHAT_RESPONSE)
        if content:
            try:
                result = json.loads(content)
                if result.get("id") == msg_id:
                    print(f"\r{' '*40}\r", end="")
                    return result
                elif result.get("id") != last_id:
                    last_id = result.get("id")
            except:
                pass
        
        # Update spinner
        elapsed = int(time.time() - start)
        print(f"\r{D}  Waiting... {elapsed}s{W}", end="", flush=True)
        time.sleep(POLL_INTERVAL)
    
    print(f"\r{' '*40}\r", end="")
    return None

def check_status():
    """Check if the agent is running by looking at recent activity"""
    # Check if response file exists and is recent
    content, _ = github_get_file(CHAT_RESPONSE)
    if content:
        try:
            result = json.loads(content)
            ts = result.get("timestamp", "")
            print(f"{G}Agent is active{W}")
            print(f"  Last response: {ts}")
            print(f"  Last ID: {result.get('id', 'unknown')}")
            return True
        except:
            pass
    
    # Check if queue has a pending message
    queue_content, _ = github_get_file(CHAT_QUEUE)
    if queue_content:
        print(f"{Y}Agent may be processing a message{W}")
        try:
            q = json.loads(queue_content)
            print(f"  Pending: {q.get('message', '?')[:80]}")
            print(f"  ID: {q.get('id', '?')}")
        except:
            pass
        return True
    
    print(f"{R}Agent appears to be offline{W}")
    print(f"  Start it in sandbox: python3 agent.py -i")
    return False

def main():
    parser = argparse.ArgumentParser(description="Kali Chat Client — SAA Agent via GitHub")
    parser.add_argument("message", nargs="?", help="Message to send to agent")
    parser.add_argument("--status", "-s", action="store_true", help="Check if agent is running")
    parser.add_argument("--wait", "-w", type=int, default=MAX_WAIT, help=f"Max wait seconds (default: {MAX_WAIT})")
    args = parser.parse_args()
    
    if not GITHUB_TOKEN:
        GITHUB_TOKEN_INPUT = input("Enter GitHub token: ").strip()
        if not GITHUB_TOKEN_INPUT:
            print(f"{R}No token provided. Set: export GITHUB_TOKEN='gho_xxx'{W}")
            sys.exit(1)
        os.environ["GITHUB_TOKEN"] = GITHUB_TOKEN_INPUT
        globals()["GITHUB_TOKEN"] = GITHUB_TOKEN_INPUT
    
    # Verify repo access
    try:
        resp = requests.get(f"https://api.github.com/repos/{REPO}",
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}"}, timeout=10)
        if resp.status_code != 200:
            print(f"{R}Cannot access repo {REPO} (HTTP {resp.status_code}){W}")
            sys.exit(1)
    except Exception as e:
        print(f"{R}Cannot reach GitHub: {e}{W}")
        sys.exit(1)
    
    if args.status:
        check_status()
        return
    
    if not args.message:
        # Read from stdin if available
        if not sys.stdin.isatty():
            args.message = sys.stdin.read().strip()
        if not args.message:
            print(f"""{C}{B}
╔══════════════════════════════════════════════════╗
║  Kali Chat → SAA Agent (GitHub Relay)            ║
╠══════════════════════════════════════════════════╣
║  Send messages to the autonomous agent in the    ║
║  sandbox. Agent executes commands and reports.   ║
╠══════════════════════════════════════════════════╣
║  Usage:                                          ║
║  python3 kali_chat.py "scan target.com"          ║
║  python3 kali_chat.py "find subdomains of x.com"  ║
║  python3 kali_chat.py --status                   ║
╚══════════════════════════════════════════════════╝{W}

{D}First: start the agent in sandbox: python3 agent.py -i{W}
{D}Then: send messages from Kali: python3 kali_chat.py "your task"{W}
""")
            return
    
    print(f"\n{M}🤖 Sending to SAA Agent...{W}")
    msg_id = send_message(args.message)
    
    if msg_id:
        print(f"{G}  [{msg_id}] Message sent{W}")
        result = get_response(msg_id, max_wait=args.wait)
        
        if result:
            print(f"\n{C}━━━ Agent Response ━━━{W}")
            response = result.get("response", "(no response)")
            print(response)
            cmds = result.get("commands_executed", 0)
            if cmds:
                print(f"\n{D}Commands executed: {cmds}{W}")
            print()
        else:
            print(f"{R}  [TIMEOUT] No response after {args.wait}s{W}")
            print(f"{Y}  Make sure agent is running: python3 agent.py -i{W}")
    else:
        print(f"{R}  [FAILED] Could not send message{W}")

if __name__ == "__main__":
    main()
