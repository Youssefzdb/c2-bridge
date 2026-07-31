#!/usr/bin/env python3
"""
Kali Shell v9 — GitHub Relay Edition (NO Cloudflare)
Run this on your Kali machine for a shell in the sandbox.

The sandbox has: nmap, sqlmap, nuclei, nikto, ffuf, gobuster, openssl, python3+scapy

Usage:
    python3 kali_shell_v9.py
    
Then type commands like:
    nmap -sT -p 443 target.com
    sqlmap -u https://target.com/?id=1 --batch
    nuclei -u https://target.com -t /root/nuclei-templates/
    nikto -h https://target.com
    gobuster dir -u https://target.com -w /usr/share/wordlists/dirb/common.txt
"""

import requests
import sys
import time
import json
import os
import base64
import uuid
from datetime import datetime

# === CONFIG ===
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "") or input("Enter GitHub token: ").strip()
REPO = "Youssefzdb/c2-bridge"
QUEUE_FILE = "c2_queue.json"
OUTPUT_FILE = "c2_output.json"
POLL_INTERVAL = 1.5

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
        print(f"  Error: {e}")
        return None, None

def github_put_file(path, content, sha=None, message="C2 command"):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {
        "message": message,
        "content": encoded,
    }
    if sha:
        payload["sha"] = sha
    try:
        resp = requests.put(url, headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }, json=payload, timeout=15)
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"  Error: {e}")
        return False

def github_delete_file(path, sha, message="C2 cleanup"):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    try:
        resp = requests.delete(url, headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }, json={"message": message, "sha": sha}, timeout=15)
        return resp.status_code in (200, 204)
    except:
        return False

def send_command(cmd):
    """Send command to sandbox via GitHub queue"""
    cmd_id = str(uuid.uuid4())[:8]
    cmd_data = {
        "id": cmd_id,
        "command": cmd,
        "status": "pending",
        "timestamp": datetime.now().isoformat()
    }
    
    # Check if queue file already exists (worker hasn't processed previous command)
    existing, existing_sha = github_get_file(QUEUE_FILE)
    if existing:
        print("  [!] Queue busy — waiting for worker to process previous command...")
        for _ in range(30):
            time.sleep(2)
            existing, existing_sha = github_get_file(QUEUE_FILE)
            if not existing:
                break
    
    # Write command to queue
    ok = github_put_file(QUEUE_FILE, json.dumps(cmd_data, indent=2), 
                         sha=existing_sha,
                         message=f"C2 cmd [{cmd_id}]")
    if not ok:
        print("  [ERROR] Failed to send command")
        return None
    return cmd_id

def get_output(cmd_id, max_wait=300):
    """Poll for output from sandbox"""
    start = time.time()
    last_output_id = None
    
    while time.time() - start < max_wait:
        content, _ = github_get_file(OUTPUT_FILE)
        if content:
            try:
                result = json.loads(content)
                if result.get("id") == cmd_id and result.get("status") == "completed":
                    return result.get("output", "(no output)")
                elif result.get("id") != cmd_id and last_output_id != result.get("id"):
                    last_output_id = result.get("id")
            except:
                pass
        time.sleep(POLL_INTERVAL)
    return "[TIMEOUT — no response from sandbox worker]"

def main():
    print("""
╔══════════════════════════════════════════════════╗
║  KALI SHELL v9 → Sandbox (GitHub Relay)          ║
║  No Cloudflare. No rate limits. Direct.          ║
╠══════════════════════════════════════════════════╣
║  Tools: nmap, sqlmap, nuclei, nikto, ffuf,      ║
║         gobuster, curl, openssl, python3+scapy   ║
║                                                  ║
║  Type 'exit' to quit | 'clear' to clear screen   ║
╚══════════════════════════════════════════════════╝
    """)
    
    while True:
        try:
            cmd = input("\033[91mkali@sandbox\033[0m:~# ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        
        if not cmd:
            continue
        if cmd.lower() in ['exit', 'quit']:
            break
        if cmd == 'clear':
            os.system('clear')
            continue
        if cmd in ['kali --list', 'kali -l', 'tools', 'help']:
            cmd = "kali --list"
        
        # Send via GitHub
        cmd_id = send_command(cmd)
        if cmd_id:
            print(f"  [{cmd_id}] Waiting for sandbox...", end="", flush=True)
            output = get_output(cmd_id)
            print("\r" + " " * 50 + "\r", end="")  # Clear waiting message
            print(output)
        else:
            print("  [ERROR] Cannot reach sandbox via GitHub")

if __name__ == "__main__":
    main()
