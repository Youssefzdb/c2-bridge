#!/usr/bin/env bash
# ════════════════════════════════════════════════
# SAA Chat — Setup & Run script for Kali Linux
# Connects to the sandbox Ollama agent via C2 bridge
# ════════════════════════════════════════════════

set -e

BRIDGE_URL="https://elio-acd17217.base44.app/functions/c2Bridge"
TOKEN="shadow-core-c2-bridge-2026"
CHAT_REMOTE="/app/conversations/6a6884ff4bc0607c4866ab4f/chat.py"

cat << 'BANNER'
╔═══════════════════════════════════════════════════╗
║  SAA Chat — Remote Sandbox Agent Connection     ║
╠═══════════════════════════════════════════════════╣
║  Connects to Ollama agent running in sandbox     ║
║  via C2 bridge. Chat + command execution.         ║
╚═══════════════════════════════════════════════════╝
BANNER

echo ""
echo "Choose model:"
echo "  1) qwen2.5-coder:7b  (fast, ~3 tokens/sec)"
echo "  2) qwen2.5-coder:32b (smart, ~1.6 tokens/sec)"
echo ""
read -p "Model [1/2, default=1]: " choice

case "$choice" in
  2) MODEL="qwen2.5-coder:32b"; echo "Using 32B (smart mode)";;
  *) MODEL="qwen2.5-coder:7b"; echo "Using 7B (fast mode)";;
esac

echo ""
echo "Choose mode:"
echo "  1) Chat only (no command execution)"
echo "  2) Chat + command execution (agent can run commands in sandbox)"
echo ""
read -p "Mode [1/2, default=2]: " mode_choice

case "$mode_choice" in
  1) EXEC_FLAG="--no-exec"; echo "Chat only mode";;
  *) EXEC_FLAG=""; echo "Chat + exec mode";;
esac

echo ""
echo "Starting chat session via C2 bridge..."
echo "Type your messages. The agent will respond and can execute commands."
echo "Press Ctrl+C to exit."
echo ""

# Send the chat command via C2 bridge (PTY mode for interactive)
CMD="python3 $CHAT_REMOTE --model $MODEL $EXEC_FLAG"

# Queue the command
RESPONSE=$(curl -s -m 10 -X POST "$BRIDGE_URL" \
  -H "Content-Type: application/json" \
  -d "{\"command\": \"PTY:$CMD\", \"token\": \"$TOKEN\"}" 2>&1)

CMD_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

if [ -z "$CMD_ID" ]; then
  echo "Error: Failed to queue command. Response: $RESPONSE"
  exit 1
fi

echo "Command queued (ID: $CMD_ID)"
echo "Waiting for agent output..."
echo ""

# Poll for output
LAST_LEN=0
while true; do
  RESULT=$(curl -s -m 10 "$BRIDGE_URL?token=$TOKEN&id=$CMD_ID" 2>&1)
  
  STATUS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  OUTPUT=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('output',''),end='')" 2>/dev/null)
  
  if [ ${#OUTPUT} -gt $LAST_LEN ]; then
    # Print only new bytes
    echo -n "${OUTPUT:$LAST_LEN}"
    LAST_LEN=${#OUTPUT}
  fi
  
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "error" ]; then
    break
  fi
  
  # Send input if user typed something (non-blocking check)
  # For simplicity, this version is output-only
  # Use the python C2 client for full bidirectional chat
  
  sleep 0.5
done

echo ""
echo "Session ended."
