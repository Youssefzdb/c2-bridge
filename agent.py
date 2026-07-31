#!/usr/bin/env python3
"""
Sandbox Autonomous Agent (SAA) v2
Autonomous AI agent running inside the sandbox using Ollama.

Usage:
  python3 agent.py "Scan 10.10.10.1 for open ports and report findings"
  python3 agent.py --interactive   # Interactive mode (GitHub relay — works through C2!)
  python3 agent.py --model qwen2.5-coder:32b --interactive

Interactive mode uses GitHub as relay (NO stdin needed):
  - Agent polls github.com/Youssefzdb/c2-bridge/agent_chat.json for messages
  - User sends messages via kali_chat.py from Kali
  - Responses written to agent_response.json
  
Author: Built by Elio for Youssef Zaidi
"""

import requests
import json
import subprocess
import sys
import os
import time
import re
import base64
import argparse
import uuid
from datetime import datetime

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5-coder:32b"
MAX_ITERATIONS = 50
MAX_OUTPUT_CHARS = 5000
MAX_HISTORY = 20
TEMPERATURE = 0.7
TIMEOUT = 120
LOG_FILE = "agent.log"
WORKSPACE = os.getcwd()

# GitHub relay config
GITHUB_TOKEN = os.environ.get("GITHUB_ACCESS_TOKEN", "")
REPO = "Youssefzdb/c2-bridge"
CHAT_QUEUE = "agent_chat.json"
CHAT_RESPONSE = "agent_response.json"
POLL_INTERVAL = 2

# Colors
R = "\033[91m"
G = "\033[92m"
Y = "\033[93m"
C = "\033[96m"
B = "\033[1m"
D = "\033[2m"
W = "\033[0m"
M = "\033[95m"

# ════════════════════════════════════════════
# SYSTEM PROMPT
# ════════════════════════════════════════════
SYSTEM_PROMPT = """You are SAA (Sandbox Autonomous Agent) — an autonomous AI agent running inside a Linux sandbox.

You are NOT a chatbot. You are an autonomous agent that completes tasks by executing commands and iterating.

## Capabilities:
- Execute bash commands (nmap, curl, python3, gobuster, nikto, nuclei, sqlmap, ffuf, openssl)
- Write and run scripts (Python, Bash)
- Read and analyze files
- Make HTTP requests
- Chain commands together
- Iterate until a task is complete

## Response Format (STRICT):
Every response MUST contain exactly ONE action block:

For executing a command:
```action
<command>
```

For marking the task as complete:
```action
DONE: <summary of what was accomplished>
```

## Rules:
1. ONLY use the action block format. No prose outside the block.
2. ONE action per response. Wait for the result before the next action.
3. If a command fails, analyze the error and try a different approach.
4. Break complex tasks into steps. Execute one step at a time.
5. Keep command output concise. Use `head`, `tail`, `grep`, `wc`.
6. When done, use `DONE:` to summarize findings.
7. Use `timeout` for long-running commands.
8. For nmap, always use `-sT -Pn` flags (sandbox doesn't support SYN scans).
9. You speak Arabic, French, and English fluently.
10. You're a cybersecurity expert — pentesting, recon, vulnerability analysis.

## Examples:

User: "Scan example.com for open ports"
You:
```action
nmap -sT -Pn -p 443,80,22,8080 --open --host-timeout 15s example.com 2>&1
```

User: "Check for subdomains"
You:
```action
curl -s "https://crt.sh/?q=%25.example.com&output=json" 2>/dev/null | python3 -c "import sys,json; data=json.load(sys.stdin); [print(e.get('name_value','')) for e in data]" | sort -u | head -30
```

Remember: Execute commands, read results, iterate, complete the task. DO IT, don't talk about it."""

# ════════════════════════════════════════════
# GITHUB RELAY
# ════════════════════════════════════════════

def github_get_file(path):
    """Get file content + SHA from GitHub"""
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
    except:
        return None, None

def github_put_file(path, content, sha=None, message="Agent update"):
    """Create or update file in GitHub"""
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
    except:
        return False

def github_delete_file(path, sha, message="Agent cleanup"):
    """Delete file from GitHub"""
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    try:
        resp = requests.delete(url, headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }, json={"message": message, "sha": sha}, timeout=15)
        return resp.status_code in (200, 204)
    except:
        return False

# ════════════════════════════════════════════
# AGENT CORE
# ════════════════════════════════════════════

class SandboxAgent:
    def __init__(self, model=MODEL, max_iterations=MAX_ITERATIONS):
        self.model = model
        self.max_iterations = max_iterations
        self.history = []
        self.task = ""
        self.iteration = 0
        self.commands_executed = 0
        self.start_time = time.time()
        
    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    
    def call_ollama(self, messages):
        """Call Ollama API (non-streaming)"""
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": TEMPERATURE,
                        "num_ctx": 32768,
                    }
                },
                timeout=300
            )
            if response.status_code == 200:
                return response.json().get("message", {}).get("content", "")
            return f"ERROR: Ollama returned {response.status_code}"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def execute_command(self, command):
        """Execute a bash command and return output"""
        self.log(f"CMD: {command[:100]}")
        self.commands_executed += 1
        
        try:
            proc = subprocess.Popen(
                command, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True, cwd=WORKSPACE
            )
            try:
                output, _ = proc.communicate(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
                output = "[TIMEOUT: 120s]"
            
            if len(output) > MAX_OUTPUT_CHARS:
                output = output[:MAX_OUTPUT_CHARS] + f"\n... [TRUNCATED]"
            
            return output.strip()
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def parse_action(self, response):
        """Extract action from LLM response"""
        match = re.search(r'```action\s*(.*?)\s*```', response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        done_match = re.search(r'DONE:\s*(.*)', response, re.DOTALL)
        if done_match:
            return f"DONE: {done_match.group(1).strip()}"
        
        lines = response.strip().split('\n')
        first_line = lines[0].strip() if lines else ""
        if first_line and not first_line.startswith('#') and len(first_line) < 500:
            return first_line
        return None
    
    def run(self, task):
        """Run the agent autonomously (single task, no interaction needed)"""
        self.task = task
        self.log(f"TASK: {task}")
        
        print(f"\n{C}{B}╔══════════════════════════════════════════════════════╗{W}")
        print(f"{C}{B}║       SANDBOX AUTONOMOUS AGENT (SAA) v2.0            ║{W}")
        print(f"{C}{B}║  Model: {self.model:<44} ║{W}")
        print(f"{C}{B}║  Task:  {task[:44]:<44} ║{W}")
        print(f"{C}{B}╚══════════════════════════════════════════════════════╝{W}\n")
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {task}\n\nStart working on this task now. Execute your first command."}
        ]
        
        while self.iteration < self.max_iterations:
            self.iteration += 1
            elapsed = time.time() - self.start_time
            print(f"\n{Y}━━━ Iteration {self.iteration}/{self.max_iterations} ({elapsed:.1f}s) ━━━{W}")
            
            if len(messages) > MAX_HISTORY * 2 + 2:
                messages = [messages[0], messages[1]] + messages[-(MAX_HISTORY * 2):]
            
            response = self.call_ollama(messages)
            if response.startswith("ERROR:"):
                print(f"{R}[!] Error: {response}{W}")
                time.sleep(2)
                response = self.call_ollama(messages)
                if response.startswith("ERROR:"):
                    break
            
            messages.append({"role": "assistant", "content": response})
            action = self.parse_action(response)
            
            if action is None:
                messages.append({"role": "user", "content": "Please use the action block format."})
                continue
            
            if action.startswith("DONE:"):
                summary = action[5:].strip()
                print(f"\n{G}{B}✅ TASK COMPLETE{W}")
                print(f"{G}{summary}{W}")
                self.log(f"DONE: {summary}")
                self.print_stats()
                return summary
            
            print(f"{C}⚡ Executing:{W} {action[:120]}")
            output = self.execute_command(action)
            print(f"{D}{output[:2000]}{W}" if output else f"{D}(no output){W}")
            
            messages.append({
                "role": "user",
                "content": f"Command output:\n```\n{output}\n```\n\nAnalyze and decide next action. Use ONE action block."
            })
        
        print(f"\n{Y}⚠️ Max iterations reached.{W}")
        self.print_stats()
        return "Max iterations reached"
    
    def print_stats(self):
        elapsed = time.time() - self.start_time
        print(f"\n{C}━━━ Stats ━━━{W}")
        print(f"  Iterations: {self.iteration}")
        print(f"  Commands:   {self.commands_executed}")
        print(f"  Time:       {elapsed:.1f}s")
        print(f"  Model:      {self.model}")
        print()
    
    def interactive_github(self):
        """
        Interactive mode via GitHub relay — NO stdin needed!
        Works through C2 bridge because it polls GitHub instead of reading stdin.
        
        Flow:
        1. Agent polls agent_chat.json on GitHub for messages
        2. When a message arrives, processes it with Ollama
        3. Executes any actions (multi-step autonomous loop)
        4. Writes response to agent_response.json
        5. Deletes the chat queue file
        6. Goes back to polling
        """
        print(f"\n{C}{B}╔══════════════════════════════════════════════════════╗{W}")
        print(f"{C}{B}║    SANDBOX AUTONOMOUS AGENT — INTERACTIVE MODE       ║{W}")
        print(f"{C}{B}╠══════════════════════════════════════════════════════╣{W}")
        print(f"{C}{B}║  Model: {self.model:<44} ║{W}")
        print(f"{C}{B}║  Mode:  GitHub Relay (no stdin needed)               ║{W}")
        print(f"{C}{B}║  Poll:  every {POLL_INTERVAL}s | Repo: {REPO:<19} ║{W}")
        print(f"{C}{B}╚══════════════════════════════════════════════════════╝{W}")
        print(f"\n{G}Waiting for messages from Kali...{W}")
        print(f"{D}Send messages via: python3 kali_chat.py 'your message'{W}")
        print(f"{D}Or through kali_shell: python3 kali_chat.py 'scan target'{W}\n")
        
        # Conversation history (persists across messages)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        last_sha = None
        
        while True:
            try:
                # Poll for chat messages
                content, sha = github_get_file(CHAT_QUEUE)
                
                if content and sha and sha != last_sha:
                    last_sha = sha
                    
                    try:
                        chat_data = json.loads(content)
                    except:
                        chat_data = {"message": content, "id": str(uuid.uuid4())[:8]}
                    
                    msg_id = chat_data.get("id", "")
                    user_msg = chat_data.get("message", "")
                    timestamp = chat_data.get("timestamp", "")
                    
                    if not user_msg:
                        time.sleep(POLL_INTERVAL)
                        continue
                    
                    print(f"\n{G}[{msg_id}] User:{W} {user_msg}")
                    self.log(f"CHAT [{msg_id}]: {user_msg}")
                    
                    # Add to conversation
                    messages.append({"role": "user", "content": f"Task: {user_msg}\n\nStart working on this now."})
                    
                    # Run autonomous loop for this message
                    response_text = self._process_message(messages, msg_id)
                    
                    # Write response to GitHub
                    result = {
                        "id": msg_id,
                        "message": user_msg,
                        "response": response_text,
                        "timestamp": datetime.now().isoformat(),
                        "commands_executed": self.commands_executed,
                    }
                    
                    _, resp_sha = github_get_file(CHAT_RESPONSE)
                    github_put_file(CHAT_RESPONSE, json.dumps(result, indent=2),
                                  sha=resp_sha, message=f"Agent response [{msg_id}]")
                    
                    # Delete queue file
                    github_delete_file(CHAT_QUEUE, sha, message=f"Chat done [{msg_id}]")
                    last_sha = None
                    
                    print(f"{G}Response sent. Waiting for next message...{W}\n")
                
                time.sleep(POLL_INTERVAL)
                
            except KeyboardInterrupt:
                print(f"\n{Y}Shutting down...{W}")
                break
            except Exception as e:
                self.log(f"Error: {e}")
                time.sleep(5)
    
    def _process_message(self, messages, msg_id):
        """Process a single message with autonomous command execution loop"""
        output_parts = []
        self.iteration = 0
        self.commands_executed = 0
        self.start_time = time.time()
        
        for i in range(self.max_iterations):
            self.iteration = i + 1
            elapsed = time.time() - self.start_time
            print(f"\n{Y}━━━ Step {self.iteration} ({elapsed:.1f}s) ━━━{W}")
            
            if len(messages) > MAX_HISTORY * 2 + 2:
                messages = [messages[0]] + messages[-(MAX_HISTORY * 2):]
            
            response = self.call_ollama(messages)
            if response.startswith("ERROR:"):
                print(f"{R}[!] LLM Error: {response}{W}")
                output_parts.append(f"[Error: {response}]")
                break
            
            messages.append({"role": "assistant", "content": response})
            action = self.parse_action(response)
            
            if action is None:
                messages.append({"role": "user", "content": "Please use the action block format."})
                continue
            
            if action.startswith("DONE:"):
                summary = action[5:].strip()
                print(f"\n{G}✅ {summary}{W}")
                output_parts.append(f"✅ {summary}")
                self.print_stats()
                return "\n".join(output_parts)
            
            print(f"{C}⚡ {action[:120]}{W}")
            output = self.execute_command(action)
            
            display = output[:2000] if output else "(no output)"
            print(f"{D}{display}{W}")
            
            output_parts.append(f"⚡ {action[:120]}\n{output[:1000]}")
            
            messages.append({
                "role": "user",
                "content": f"Command output:\n```\n{output}\n```\n\nAnalyze and decide next action."
            })
        
        output_parts.append(f"[Max iterations reached]")
        self.print_stats()
        return "\n".join(output_parts)


# ════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Sandbox Autonomous Agent v2")
    parser.add_argument("task", nargs="?", help="Task to complete (autonomous mode)")
    parser.add_argument("--interactive", "-i", action="store_true", 
                       help="Interactive mode via GitHub relay (works through C2 bridge)")
    parser.add_argument("--model", "-m", default=MODEL, help=f"Ollama model (default: {MODEL})")
    parser.add_argument("--max-iter", type=int, default=MAX_ITERATIONS, help=f"Max iterations (default: {MAX_ITERATIONS})")
    args = parser.parse_args()
    
    # Check Ollama
    try:
        r = requests.get(f"{OLLAMA_URL}/api/version", timeout=5)
        if r.status_code != 200:
            print(f"{R}[!] Ollama not responding{W}")
            sys.exit(1)
    except:
        print(f"{R}[!] Cannot connect to Ollama at {OLLAMA_URL}{W}")
        print(f"    Start: LD_LIBRARY_PATH=/usr/local/lib/ollama ollama serve")
        sys.exit(1)
    
    agent = SandboxAgent(model=args.model, max_iterations=args.max_iter)
    
    if args.interactive:
        if not GITHUB_TOKEN:
            print(f"{R}[!] GITHUB_ACCESS_TOKEN not set. Required for interactive mode.{W}")
            sys.exit(1)
        agent.interactive_github()
    elif args.task:
        agent.run(args.task)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
