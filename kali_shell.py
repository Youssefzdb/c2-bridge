#!/usr/bin/env python3
"""
Kali Shell — Run this on your Kali machine to get a shell in the sandbox.
The sandbox has nmap, sqlmap, nuclei, nikto, gobuster, ffuf installed.

Usage:
    python3 kali_shell.py
    
Then just type commands like you would in Kali:
    nmap -sT -p 443 target.com
    sqlmap -u https://target.com/?id=1 --batch
    nuclei -u https://target.com
"""

import requests
import sys
import time
import os

BRIDGE_URL = "https://elio-acd17217.base44.app/functions/c2Bridge"
TOKEN = "shadow-core-c2-bridge-2026"

def send_command(cmd):
    """Send command to sandbox"""
    try:
        resp = requests.post(f"{BRIDGE_URL}?token={TOKEN}",
            json={"command": cmd, "token": TOKEN}, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("id")
    except Exception as e:
        print(f"Connection error: {e}")
    return None

def get_output(cmd_id, max_wait=60):
    """Get command output"""
    for _ in range(max_wait):
        try:
            resp = requests.get(f"{BRIDGE_URL}?token={TOKEN}&id={cmd_id}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("output"):
                    return data["output"]
        except:
            pass
        time.sleep(0.5)
    return "[TIMEOUT]"

def main():
    print("""
╔══════════════════════════════════════════════════╗
║  KALI SHELL → Sandbox (Nethunter Rootless)      ║
╠══════════════════════════════════════════════════╣
║  Tools: nmap, sqlmap, nuclei, nikto, ffuf,      ║
║         gobuster, curl, openssl, python3        ║
║  Custom: pentest_toolkit.py, pentest_agent.py   ║
║                                                  ║
║  Type 'kali --list' to see all tools            ║
║  Type 'exit' to quit                             ║
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
        if cmd == 'kali --list' or cmd == 'kali -l':
            # Show available tools
            cmd = 'kali --list'
        
        # Send to sandbox
        cmd_id = send_command(cmd)
        if cmd_id:
            output = get_output(cmd_id)
            print(output)
        else:
            print("[ERROR] Cannot reach sandbox")

if __name__ == "__main__":
    main()
