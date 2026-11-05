#!/usr/bin/env bash
# One collection cycle. Used by fetch.yml (once per scheduled run) and poll.yml (every few minutes, for hours).
#
#  1. start from what is published (git reset to origin), so a long-running poller never carries stale state;
#  2. fetch the sources, parse them, and let tools/svc_auto.py decide whether the county's SVC precinct file has appeared;
#  3. commit and push ONLY if something other than the attempt log changed (a new snapshot, new tables, svc state).
#     The log gets a line on every attempt, so committing it every cycle would put a commit in the history every few minutes;
#  4. start other workflows only when needed: pages after a new county tally, svc-rehearsal when the SVC file appears.
# Nothing here may stop collection: every step after the fetch is allowed to fail on its own.
#
# Environment: CONFIG, ELECTION, BRANCH, PYTHON (defaults below); GH_TOKEN enables the workflow dispatches.
set -u
CONFIG="${CONFIG:-config/sources.json}"
ELECTION="${ELECTION:-2026-11-03-general}"
BRANCH="${BRANCH:-main}"
PYTHON="${PYTHON:-python}"
LOG="data/raw/$ELECTION/fetch_log.jsonl"
NAME="election-collector"; EMAIL="actions@users.noreply.github.com"

git fetch -q origin "$BRANCH" && git reset -q --hard "origin/$BRANCH" || echo "WARNING: could not sync with origin"

"$PYTHON" -m collect.fetch "$CONFIG" data/raw || echo "WARNING: fetch reported errors (see the log)"
"$PYTHON" -m parse.election "$ELECTION" || echo "WARNING: parse failed; the raw snapshots are still saved"
DECISION="$(mktemp)"
"$PYTHON" -m tools.svc_auto "$CONFIG" "$LOG" data/svc_auto/state.json data/rehearsal "$DECISION" || echo "WARNING: svc_auto failed"

# add only paths that exist: a missing path makes `git add` fail
for d in data/raw data/tidy data/svc_auto; do [ -e "$d" ] && git add "$d"; done
CHANGED="$(git diff --cached --name-only | grep -v 'fetch_log\.jsonl$' || true)"
PUSHED=0
if [ -z "$CHANGED" ]; then
  echo "nothing new (only the attempt log changed)"
else
  git -c user.name="$NAME" -c user.email="$EMAIL" commit -q -m "data: new snapshots $(date -u +%Y-%m-%dT%H:%MZ)"
  for i in 1 2 3 4; do
    if git pull -q --rebase origin "$BRANCH" && git push -q origin "HEAD:$BRANCH"; then PUSHED=1; break; fi
    sleep $((i * 5))
  done
  [ "$PUSHED" = 1 ] && echo "pushed: $(echo "$CHANGED" | wc -l | tr -d ' ') changed files" || echo "WARNING: push failed after 4 tries"
fi

dispatch() { # dispatch <workflow file> [gh args...]; never fatal
  if command -v gh >/dev/null 2>&1 && [ -n "${GH_TOKEN:-}" ]; then
    gh workflow run "$@" --ref "$BRANCH" || echo "WARNING: could not start $1"
  else
    echo "would start: $*"
  fi
}
if [ "$PUSHED" = 1 ] && echo "$CHANGED" | grep -q 'rrcc_api_counter_data'; then
  echo "new county tally: rebuilding the site"
  dispatch pages.yml
fi
URL="$(sed -n 's/^url=//p' "$DECISION" | tail -1)"
if grep -q '^trigger=true' "$DECISION" 2>/dev/null && [ -n "$URL" ]; then
  echo "the county's SVC precinct file is there: starting the pipeline for $URL"
  dispatch svc-rehearsal.yml -f url="$URL"
fi
exit 0
