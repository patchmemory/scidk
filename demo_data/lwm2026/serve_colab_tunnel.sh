#!/usr/bin/env bash
# serve_colab_tunnel.sh: expose the demo VM's Neo4j Bolt port through an ngrok
# TCP tunnel so Google Colab notebooks can reach the graph.
#
# Before the first run:
#   1. ngrok account with a payment card added (required for TCP endpoints,
#      even on the free plan; the card isn't charged)
#   2. ngrok config add-authtoken <token>
#
# Run on the demo VM and leave it running during the session; Ctrl-C closes it:
#   bash serve_colab_tunnel.sh
set -euo pipefail
PORT="${NEO4J_BOLT_PORT:-7687}"

command -v ngrok >/dev/null || { echo "ngrok not installed: https://ngrok.com/download"; exit 1; }
(exec 3<>/dev/tcp/127.0.0.1/"$PORT") 2>/dev/null || { echo "Nothing listening on localhost:$PORT (is Neo4j running?)"; exit 1; }

ngrok tcp "$PORT" --log=stdout > ngrok.log 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null; echo; echo "Tunnel closed."' EXIT INT TERM

URL=""
for _ in $(seq 1 20); do
  URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c \
    'import sys,json; t=json.load(sys.stdin).get("tunnels",[]); print(t[0]["public_url"] if t else "")' 2>/dev/null || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] || { echo "Tunnel didn't come up; see ngrok.log"; exit 1; }

ADDR="${URL#tcp://}"
echo "Tunnel up: localhost:$PORT -> $ADDR"
echo
echo "Give attendees this address for the notebook prompt:  $ADDR"
echo "(the notebook connects with bolt://$ADDR; use bolt://, not neo4j://)"
echo
echo "Ctrl-C to close the tunnel."
wait $PID
