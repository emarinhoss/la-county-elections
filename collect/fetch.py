"""Download each source in config/sources.json and save a raw snapshot if it changed.

Layout:  data/raw/<election>/<source_id>/<UTC timestamp>/{body, manifest.json}
Every attempt (saved, unchanged or failed) is appended to data/raw/<election>/fetch_log.jsonl.
Raw snapshots are never edited after they are written.
"""
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "la-county-elections-collector (public research project)"
TIMEOUT_S = 60
DEFAULT_MAX_BYTES = 30_000_000  # raw snapshots are committed to git, so refuse huge files


def now_utc():
    return datetime.now(timezone.utc)


def latest_hash(source_dir):
    """sha256 of the newest saved snapshot for a source, or None."""
    if not source_dir.exists():
        return None
    snaps = sorted(p for p in source_dir.iterdir() if (p / "manifest.json").exists())
    if not snaps:
        return None
    return json.loads((snaps[-1] / "manifest.json").read_text())["sha256"]


def download(url, method="GET", max_bytes=DEFAULT_MAX_BYTES):
    """Return (status, headers, body). Body is None for HEAD. Reads at most max_bytes + 1 bytes."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        body = None if method == "HEAD" else resp.read(max_bytes + 1)
        return resp.status, resp.headers, body


def fetch_source(source, election_dir, now=None):
    """Fetch one source. Returns the log entry (a dict)."""
    now = now or now_utc()
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    entry = {"source_id": source["id"], "url": source["url"], "fetched_at": now.isoformat()}
    probe = source.get("head", False)  # probe only: record status and size, never store the body
    max_bytes = source.get("max_bytes", DEFAULT_MAX_BYTES)
    try:
        status, headers, body = download(source["url"], "HEAD" if probe else "GET", max_bytes)
    except urllib.error.HTTPError as e:  # e.g. 404 for a file the county has not published yet
        entry.update(result="error", http_status=e.code, error=f"HTTPError: HTTP Error {e.code}: {e.reason}")
        return entry
    except Exception as e:  # network errors must not stop the other sources
        entry.update(result="error", error=f"{type(e).__name__}: {e}")
        return entry

    ctype = headers.get("Content-Type", "")
    if probe:
        entry.update(result="probed", http_status=status, content_type=ctype,
                     content_length=headers.get("Content-Length"), last_modified=headers.get("Last-Modified"))
        return entry
    if len(body) > max_bytes:
        entry.update(result="too_large", http_status=status, content_type=ctype,
                     content_length=headers.get("Content-Length"), error=f"more than {max_bytes} bytes, not saved")
        return entry

    digest = hashlib.sha256(body).hexdigest()
    entry.update(http_status=status, content_type=ctype, bytes=len(body), sha256=digest)
    source_dir = election_dir / source["id"]
    if digest == latest_hash(source_dir):
        entry["result"] = "unchanged"
        return entry

    snap_dir = source_dir / stamp
    snap_dir.mkdir(parents=True, exist_ok=False)
    (snap_dir / "body").write_bytes(body)
    (snap_dir / "manifest.json").write_text(json.dumps(entry, indent=2) + "\n")
    entry["result"] = "saved"
    entry["snapshot"] = stamp
    return entry


def run(config_path, data_root):
    config = json.loads(Path(config_path).read_text())
    election_dir = Path(data_root) / config["election"]
    election_dir.mkdir(parents=True, exist_ok=True)
    entries = [fetch_source(s, election_dir) for s in config["sources"]]
    with open(election_dir / "fetch_log.jsonl", "a") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return entries


if __name__ == "__main__":
    config = sys.argv[1] if len(sys.argv) > 1 else "config/sources.json"
    root = sys.argv[2] if len(sys.argv) > 2 else "data/raw"
    results = run(config, root)
    for e in results:
        print(e["source_id"], e["result"], e.get("error", ""))
    # Exit 0 even if some sources failed: the log records it, and a flaky county
    # server should not turn the whole schedule red. Fail only if every source failed.
    sys.exit(1 if all(e["result"] in ("error", "too_large") for e in results) else 0)
