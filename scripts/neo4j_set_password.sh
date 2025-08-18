#!/bin/sh
# Neo4j password change helper for SciDK
#
# Usage:
#   scripts/neo4j_set_password.sh <new_password> [--current <current_password>] [--user neo4j] [--host bolt://localhost:7687]
#   scripts/neo4j_set_password.sh <new_password> --container scidk-neo4j [--current <current_password>] [--user neo4j]
#
# Notes:
# - If your Neo4j is running via docker compose (container name scidk-neo4j), pass --container scidk-neo4j
# - If you set NEO4J_AUTH=user/pass before first start, that already sets the initial password.
# - This script uses cypher-shell and runs: ALTER CURRENT USER SET PASSWORD FROM '<old>' TO '<new>'
# - For initial login when Neo4j forces a change, the current password is often the one set in NEO4J_AUTH or the temporary one.

set -eu

if [ $# -lt 1 ]; then
  echo "Usage: $0 <new_password> [--current <current_password>] [--user neo4j] [--host bolt://localhost:7687] [--container <name>]" 1>&2
  exit 2
fi

NEW_PASS="$1"
shift

CURRENT_PASS="${NEO4J_PASSWORD:-}"
USER_NAME="${NEO4J_USER:-neo4j}"
HOST_URI="${NEO4J_URI:-bolt://localhost:7687}"
CONTAINER=""

while [ $# -gt 0 ]; do
  case "$1" in
    --current)
      CURRENT_PASS="$2"; shift 2 ;;
    --user)
      USER_NAME="$2"; shift 2 ;;
    --host)
      HOST_URI="$2"; shift 2 ;;
    --container)
      CONTAINER="$2"; shift 2 ;;
    *)
      echo "Unknown argument: $1" 1>&2; exit 2 ;;
  esac
done

if [ -z "${CURRENT_PASS}" ]; then
  # Try to derive from NEO4J_AUTH if present
  if [ -n "${NEO4J_AUTH:-}" ] && echo "$NEO4J_AUTH" | grep -q "/"; then
    CURRENT_PASS="${NEO4J_AUTH#*/}"
  else
    echo "ERROR: Current password not provided. Use --current <password> or set NEO4J_PASSWORD/NEO4J_AUTH." 1>&2
    exit 3
  fi
fi

CY_CMD="ALTER CURRENT USER SET PASSWORD FROM '$CURRENT_PASS' TO '$NEW_PASS'"

run_local() {
  if ! command -v cypher-shell >/dev/null 2>&1; then
    echo "ERROR: cypher-shell not found in PATH. Install Neo4j client or run with --container." 1>&2
    exit 4
  fi
  cypher-shell -u "$USER_NAME" -p "$CURRENT_PASS" -a "$HOST_URI" "$CY_CMD"
}

run_container() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker not found. Install Docker or run locally without --container." 1>&2
    exit 5
  fi
  docker exec -e NEO4J_USERNAME="$USER_NAME" -e NEO4J_PASSWORD="$CURRENT_PASS" "$CONTAINER" \
    cypher-shell -u "$USER_NAME" -p "$CURRENT_PASS" "$CY_CMD"
}

if [ -n "$CONTAINER" ]; then
  run_container
else
  run_local
fi

echo "Password updated for user '$USER_NAME'."
