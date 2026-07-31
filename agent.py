#!/usr/bin/env python3
"""
Sandbox Autonomous Agent (SAA)
A self-directed AI agent running inside the sandbox using Ollama.
Can execute bash commands, loop, iterate, and complete tasks autonomously.
Like having a mini-Elio inside the sandbox.

Usage:
  python3 agent.py "Scan 10.10.10.1 for open ports and report findings"
  python3 agent.py "Find all SQL injection vulnerabilities in http://target.com"
  python3 agent.py "Build a Python port scanner and test it"
  python3 agent.py --interactive   # Interactive mode
  
Author: Built by Elio for Youssef Zaidi
"""

import requests
import json
import subprocess
import sys
import os
import time
import re
import argparse
from datetime import datetime

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5-coder:32b"
MAX_ITERATIONS = 50
MAX_OUTPUT_CHARS = 5000  # Truncate command output to fit in context
MAX_HISTORY = 20  # Keep last N interactions in context
TEMPERATURE = 0.7
TIMEOUT = 120  # Command timeout in seconds
LOG_FILE = "agent.log"
WORKSPACE = os.getcwd()

# Colors
R = "\033[91m"
G = "\033[92m"
Y = "\033[93m"
C = "\033[96m"
B = "\033[1m"
D = "\033[2m"
W = "\033[0m"

# ════════════════════════════════════════════
# SYSTEM PROMPT — This makes it an AGENT not just a chatbot
# ════════════════════════════════════════════
SYSTEM_PROMPT = """You are SAA (Sandbox Autonomous Agent) — an autonomous AI agent running inside a Linux sandbox environment.

You are NOT a chatbot. You are an autonomous agent that completes tasks by executing commands and iterating.

## Your Capabilities:
- Execute bash commands (nmap, curl, python3, gobuster, nikto, etc.)
- Write and run scripts (Python, Bash)
- Read and analyze files
- Make HTTP requests
- Chain commands together
- Iterate until a task is complete

## Response Format (STRICT — you MUST follow this):
Every response MUST contain exactly ONE action block:

For executing a command:
```action
<command>
```

For marking the task as complete:
```action
DONE: <summary of what was accomplished>
```

For asking a clarifying question (use sparingly):
```action
ASK: <question>
```

## Rules:
1. ONLY use the action block format above. No prose outside the block.
2. ONE action per response. Wait for the result before the next action.
3. If a command fails, analyze the error and try a different approach.
4. Break complex tasks into steps. Execute one step at a time.
5. Be resourceful. If a tool isn't installed, install it or find an alternative.
6. Keep command output concise. Use `head`, `tail`, `grep`, `wc` to limit output.
7. When you have enough information, use `DONE:` to summarize.
8. For long-running commands, use `timeout` to prevent hangs.
9. You can write scripts to files and then execute them.
10. Think step by step inside the action block before the command.

## Examples:

User: "Scan 10.10.10.1 for open ports"
You:
```action
nmap -sS -p- --min-rate 1000 10.10.10.1 | head -50
```

User: "Find subdomains of example.com"
You:
```action
python3 -c "
import subprocess
result = subprocess.run(['curl', '-s', 'https://crt.sh/?q=%25.example.com&output=json'], capture_output=True, text=True)
import json
data = json.loads(result.stdout)
names = set()
for entry in data:
    for name in entry.get('name_value','').split('\n'):
        names.add(name.strip())
for n in sorted(names):
    print(n)
" 2>/dev/null | head -30
```

User: "Check for SQL injection"
You:
```action
python3 -c "
import requests
url = 'http://target.com/page?id=1'
payloads = ['1\\'', '1 OR 1=1', \"1' OR '1'='1\", '1 UNION SELECT 1--']
for p in payloads:
    r = requests.get(url.replace('1', p), timeout=5)
    if 'error' in r.text.lower() or 'sql' in r.text.lower():
        print(f'[VULN] Payload: {p}')
    print(f'[INFO] Tested: {p} (status: {r.status_code}, len: {len(r.text)})')
"
```

Remember: You are an autonomous agent. Execute commands, read results, iterate, and complete the task. Don't just talk about it — DO IT."""

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
        print(f"{D}{line}{W}", flush=True)
    
    def call_ollama(self, messages):
        """Call Ollama API"""
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
            else:
                return f"ERROR: Ollama returned {response.status_code}: {response.text[:200]}"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def execute_command(self, command):
        """Execute a bash command and return output"""
        self.log(f"CMD: {command[:100]}")
        self.commands_executed += 1
        
        try:
            # Add timeout to prevent hangs
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=WORKSPACE
            )
            
            try:
                output, _ = proc.communicate(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
                output = proc.stdout.read() if proc.stdout else ""
                output += f"\n[TIMEOUT: Command exceeded {TIMEOUT}s]"
            
            # Truncate output
            if len(output) > MAX_OUTPUT_CHARS:
                output = output[:MAX_OUTPUT_CHARS] + f"\n... [TRUNCATED: {len(output)} total chars]"
            
            return output.strip()
        except Exception as e:
            return f"EXECUTION ERROR: {str(e)}"
    
    def parse_action(self, response):
        """Extract action from LLM response"""
        # Look for ```action ... ``` block
        match = re.search(r'```action\s*(.*?)\s*```', response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Fallback: look for DONE: or ASK: anywhere
        done_match = re.search(r'DONE:\s*(.*)', response, re.DOTALL)
        if done_match:
            return f"DONE: {done_match.group(1).strip()}"
        
        ask_match = re.search(r'ASK:\s*(.*)', response, re.DOTALL)
        if ask_match:
            return f"ASK: {ask_match.group(1).strip()}"
        
        # If no action block found, try to use the whole response as a command
        # (but only if it looks like a command)
        lines = response.strip().split('\n')
        first_line = lines[0].strip() if lines else ""
        if first_line and not first_line.startswith('#') and len(first_line) < 500:
            return first_line
        
        return None
    
    def run(self, task):
        """Run the agent loop"""
        self.task = task
        self.log("=" * 60)
        self.log(f"TASK: {task}")
        self.log(f"Model: {self.model}")
        self.log(f"Max iterations: {self.max_iterations}")
        self.log("=" * 60)
        
        print(f"\n{C}{B}╔══════════════════════════════════════════════════════╗{W}")
        print(f"{C}{B}║       SANDBOX AUTONOMOUS AGENT (SAA) v1.0            ║{W}")
        print(f"{C}{B}╠══════════════════════════════════════════════════════╣{W}")
        print(f"{C}{B}║  Model: {self.model:<44} ║{W}")
        print(f"{C}{B}║  Task:  {task[:44]:<44} ║{W}")
        print(f"{C}{B}╚══════════════════════════════════════════════════════╝{W}\n")
        
        # Build initial messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {task}\n\nStart working on this task now. Execute your first command."}
        ]
        
        while self.iteration < self.max_iterations:
            self.iteration += 1
            elapsed = time.time() - self.start_time
            
            print(f"\n{Y}━━━ Iteration {self.iteration}/{self.max_iterations} ({elapsed:.1f}s elapsed) ━━━{W}")
            
            # Trim history if too long
            if len(messages) > MAX_HISTORY * 2 + 2:
                # Keep system + first user + last N exchanges
                messages = [messages[0], messages[1]] + messages[-(MAX_HISTORY * 2):]
            
            # Call LLM
            self.log(f"Calling LLM (iteration {self.iteration})...")
            print(f"{D}🤔 Thinking...{W}", flush=True, end="\r")
            
            response = self.call_ollama(messages)
            
            if response.startswith("ERROR:"):
                print(f"{R}[!] LLM Error: {response}{W}")
                self.log(f"LLM Error: {response}")
                # Retry once
                time.sleep(2)
                response = self.call_ollama(messages)
                if response.startswith("ERROR:"):
                    print(f"{R}[!] LLM failed twice. Stopping.{W}")
                    break
            
            # Clear thinking indicator
            print(" " * 30, end="\r")
            
            # Add to messages
            messages.append({"role": "assistant", "content": response})
            
            # Parse action
            action = self.parse_action(response)
            
            if action is None:
                print(f"{Y}[!] No action found in response. Retrying...{W}")
                self.log("No action found in response")
                messages.append({"role": "user", "content": "Please respond with exactly ONE action block (```action ... ```). Execute a command or use DONE:/ASK:."})
                continue
            
            # Check for completion
            if action.startswith("DONE:"):
                summary = action[5:].strip()
                print(f"\n{G}{B}✅ TASK COMPLETE{W}")
                print(f"{G}Summary: {summary}{W}")
                self.log(f"DONE: {summary}")
                self.print_stats()
                return summary
            
            # Check for question
            if action.startswith("ASK:"):
                question = action[4:].strip()
                print(f"\n{Y}❓ Agent asks: {question}{W}")
                self.log(f"ASK: {question}")
                # In autonomous mode, we auto-answer "proceed with best guess"
                messages.append({"role": "user", "content": "Use your best judgment and proceed. Don't ask questions — make reasonable assumptions and continue."})
                continue
            
            # Execute the command
            print(f"{C}⚡ Executing:{W} {action[:120]}")
            output = self.execute_command(action)
            
            if output:
                # Show output (truncated for display)
                display = output[:2000]
                if len(output) > 2000:
                    display += "..."
                print(f"{D}{display}{W}")
            else:
                print(f"{D}(no output){W}")
            
            # Feed output back to LLM
            messages.append({
                "role": "user",
                "content": f"Command output:\n```\n{output}\n```\n\nAnalyze this output and decide your next action. Use ONE action block."
            })
        
        # Max iterations reached
        print(f"\n{Y}⚠️  Max iterations ({self.max_iterations}) reached.{W}")
        self.print_stats()
        return "Max iterations reached"
    
    def print_stats(self):
        elapsed = time.time() - self.start_time
        print(f"\n{C}━━━ Agent Stats ━━━{W}")
        print(f"  Iterations:       {self.iteration}")
        print(f"  Commands executed: {self.commands_executed}")
        print(f"  Time elapsed:     {elapsed:.1f}s")
        print(f"  Model:            {self.model}")
        print(f"  Log file:         {LOG_FILE}")
        print()
    
    def interactive(self):
        """Interactive REPL mode"""
        print(f"\n{C}{B}╔══════════════════════════════════════════════════════╗{W}")
        print(f"{C}{B}║    SANDBOX AUTONOMOUS AGENT — INTERACTIVE MODE       ║{W}")
        print(f"{C}{B}╠══════════════════════════════════════════════════════╣{W}")
        print(f"{C}{B}║  Model: {self.model:<44} ║{W}")
        print(f"{C}{B}║  Type 'exit' to quit, 'status' for stats           ║{W}")
        print(f"{C}{B}╚══════════════════════════════════════════════════════╝{W}\n")
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        
        while True:
            try:
                task = input(f"{G}You> {W}")
                if not task.strip():
                    continue
                if task.lower() in ("exit", "quit"):
                    break
                if task.lower() == "status":
                    self.print_stats()
                    continue
                
                # Run as a sub-task
                self.iteration = 0
                self.commands_executed = 0
                self.start_time = time.time()
                
                # Add task to messages (continue same conversation)
                messages.append({"role": "user", "content": f"Task: {task}\n\nStart working on this task now."})
                
                # Run iterations
                for i in range(self.max_iterations):
                    self.iteration = i + 1
                    elapsed = time.time() - self.start_time
                    print(f"\n{Y}━━━ Step {self.iteration} ({elapsed:.1f}s) ━━━{W}")
                    
                    response = self.call_ollama(messages)
                    if response.startswith("ERROR:"):
                        print(f"{R}[!] Error: {response}{W}")
                        break
                    
                    messages.append({"role": "assistant", "content": response})
                    action = self.parse_action(response)
                    
                    if action is None:
                        messages.append({"role": "user", "content": "Please use the action block format."})
                        continue
                    
                    if action.startswith("DONE:"):
                        print(f"\n{G}✅ {action[5:].strip()}{W}\n")
                        break
                    
                    if action.startswith("ASK:"):
                        print(f"{Y}❓ {action[4:].strip()}{W}")
                        messages.append({"role": "user", "content": "Use your best judgment and proceed."})
                        continue
                    
                    print(f"{C}⚡ {action[:120]}{W}")
                    output = self.execute_command(action)
                    print(f"{D}{output[:2000]}{W}" if output else f"{D}(no output){W}")
                    
                    messages.append({
                        "role": "user",
                        "content": f"Output:\n```\n{output}\n```\n\nNext action?"
                    })
                
            except KeyboardInterrupt:
                print(f"\n{Y}Press 'exit' to quit{W}")
            except EOFError:
                break
        
        print(f"{Y}Goodbye!{W}")


# ════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Sandbox Autonomous Agent")
    parser.add_argument("task", nargs="?", help="Task to complete")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--model", "-m", default=MODEL, help=f"Ollama model (default: {MODEL})")
    parser.add_argument("--max-iter", type=int, default=MAX_ITERATIONS, help=f"Max iterations (default: {MAX_ITERATIONS})")
    args = parser.parse_args()
    
    # Check if Ollama is running
    try:
        r = requests.get(f"{OLLAMA_URL}/api/version", timeout=5)
        if r.status_code != 200:
            print(f"{R}[!] Ollama server not responding{W}")
            sys.exit(1)
    except:
        print(f"{R}[!] Cannot connect to Ollama at {OLLAMA_URL}{W}")
        print(f"{Y}    Start it with: ollama serve{W}")
        sys.exit(1)
    
    agent = SandboxAgent(model=args.model, max_iterations=args.max_iter)
    
    if args.interactive:
        agent.interactive()
    elif args.task:
        agent.run(args.task)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
