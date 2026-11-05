"""Decide whether the 2026 SVC precinct PDF has appeared and the pipeline should be started.

The fetch workflow probes the file every run (HEAD request, nothing stored) and logs the answer. This script reads the newest
probe for each source flagged "auto_svc" in config/sources.json and says whether to dispatch the svc-rehearsal workflow:
  - the probe must be HTTP 200 with a PDF content type and a size that is plausible for a precinct report;
  - a version of the file (size + Last-Modified) is processed once. A changed version is processed again, because the county
    may publish an early file first and replace it;
  - if a run did not produce its output, retry at most MAX_ATTEMPTS times, COOLDOWN_MIN minutes apart, then give up until
    the file changes. This never loops forever.
State lives in data/svc_auto/state.json so every fetch run (a fresh checkout) sees what was already tried.

Usage: python -m tools.svc_auto <config> <fetch_log.jsonl> <state.json> <output root> [github_output_file]
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

MIN_BYTES = 1_000_000  # the 2024 precinct report is 61 MB; a stub or error page is far smaller
MAX_ATTEMPTS = 3
COOLDOWN_MIN = 60


def latest_probe(log_lines, source_id):
    entry = None
    for line in log_lines:
        if line.strip():
            e = json.loads(line)
            if e.get("source_id") == source_id:
                entry = e
    return entry


def signature(entry):
    return f"{entry.get('content_length')}|{entry.get('last_modified')}"


def output_exists(url, out_root):
    return (Path(out_root) / Path(url).stem / "countywide_checks.csv").exists()


def decide(entry, url, state, now, out_root):
    """(trigger?, reason). Does not change `state`."""
    if entry is None:
        return False, "no probe in the log yet"
    if entry.get("result") != "probed" or entry.get("http_status") != 200:
        return False, f"not published (probe: {entry.get('result')} {entry.get('http_status')})"
    length = int(entry.get("content_length") or 0)
    if "pdf" not in (entry.get("content_type") or "").lower() or length < MIN_BYTES:
        return False, f"200 but does not look like the precinct PDF ({entry.get('content_type')}, {length} bytes)"
    prior = state.get(url)
    if prior is None or prior["signature"] != signature(entry):
        return True, "new or changed file"
    if output_exists(url, out_root):
        return False, "this version was already processed"
    if prior["attempts"] >= MAX_ATTEMPTS:
        return False, f"gave up after {MAX_ATTEMPTS} attempts on this version; waiting for the file to change"
    if now - datetime.fromisoformat(prior["last_attempt"]) < timedelta(minutes=COOLDOWN_MIN):
        return False, "last attempt was under an hour ago"
    return True, f"retrying (attempt {prior['attempts'] + 1} of {MAX_ATTEMPTS})"


def record_attempt(state, url, entry, now):
    prior = state.get(url)
    same = prior is not None and prior["signature"] == signature(entry)
    state[url] = {"signature": signature(entry), "attempts": (prior["attempts"] if same else 0) + 1, "last_attempt": now.isoformat()}


def run(config_path, log_path, state_path, out_root, now=None):
    """Returns the list of URLs to dispatch. Updates the state file for each."""
    now = now or datetime.now(timezone.utc)
    config = json.loads(Path(config_path).read_text())
    log = Path(log_path).read_text().splitlines() if Path(log_path).exists() else []
    sp = Path(state_path)
    state = json.loads(sp.read_text()) if sp.exists() else {}
    urls = []
    for src in config["sources"]:
        if not src.get("auto_svc"):
            continue
        entry = latest_probe(log, src["id"])
        go, reason = decide(entry, src["url"], state, now, out_root)
        print(f"{src['id']}: {'START' if go else 'no'} - {reason}")
        if go:
            record_attempt(state, src["url"], entry, now)
            urls.append(src["url"])
    if urls:
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(state, indent=2) + "\n")
    return urls


if __name__ == "__main__":
    config, log, state, out_root = sys.argv[1:5]
    urls = run(config, log, state, out_root)
    if len(sys.argv) > 5:  # GITHUB_OUTPUT
        with open(sys.argv[5], "a") as f:
            f.write(f"trigger={'true' if urls else 'false'}\nurl={urls[0] if urls else ''}\n")
