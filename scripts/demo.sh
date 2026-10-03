#!/usr/bin/env bash
# Walks through the assignment's example conversation against a running API.
# Usage: ./scripts/demo.sh            (BASE_URL defaults to http://localhost:8000)
#        USER_ID=rahul ./scripts/demo.sh
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost:8000}"
USER_ID="${USER_ID:-rahul-$(date +%s)}"

pretty() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import json,sys
d=json.load(sys.stdin)
keys=["response","context_used","intent","life_areas","memory_updates","missing_profile_fields","llm_provider","degraded","warnings"]
print(json.dumps({k:d[k] for k in keys if k in d} if "response" in d else d, indent=2, ensure_ascii=False))'
  else
    cat; echo
  fi
}

if [ -t 1 ]; then C='\033[1;36m'; R='\033[0m'; else C=''; R=''; fi
say() {  # session, message
  printf "\n${C}[%s] USER:${R} %s\n" "$1" "$2"
  curl -sS -X POST "$BASE_URL/chat" -H 'Content-Type: application/json' \
    -d "$(printf '{"user_id":"%s","session_id":"%s","message":"%s"}' "$USER_ID" "$1" "$2")" | pretty
}

echo "== Health"; curl -sS "$BASE_URL/health" | pretty
echo "== Demo user: $USER_ID"

echo; echo "################ First conversation ################"
say session-1 "My name is Rahul. I was born on 15 August 1995 in Delhi. I'm planning to switch jobs next year."
say session-1 "What should I focus on for my career?"
say session-1 "Why do you say that?"

echo; echo "################ New conversation ################"
say session-2 "What do you remember about my career goals?"
say session-2 "I'm preparing for a product management interview next month."
say session-2 "How is my health looking this year?"
say session-2 "Actually, I plan to switch jobs in 2028, not next year."
say session-2 "Thanks!"

echo; echo "################ Shared Brain for $USER_ID ################"
curl -sS "$BASE_URL/users/$USER_ID/brain" | pretty
