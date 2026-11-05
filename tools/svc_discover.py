"""Daily search for the real file name of this election's SVC precinct PDF.

fetch.yml probes one guessed name every run. The county's real names vary between elections (seen: 4306_final_svc_precinct_public,
4324_final_svc_precinct_public, 4291_svc_precinct_zbc, 4324_final_svc_district_v3), so once a day this looks harder:
  1. harvest: read a few county pages and follow links on the county's own hosts (bounded: MAX_PAGES pages, depth 2) and collect
     every link to a PDF under /docs/rrcc/svc/;
  2. probe: HEAD-check those links plus a systematic set of likely names built from the patterns above.
A file is started only if it is for THIS election, is a precinct report, is not a "zbc" file (zero-ballot report, produced before
the election), and looks like the real PDF (HTTP 200, PDF type, at least 1 MB). It then goes through the same once-per-version and
retry-limit rules as tools.svc_auto. A name that fetch.yml already watches is left to fetch.yml.

Usage: python -m tools.svc_discover <election folder name> [github_output_file]
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from tools.svc_auto import decide, record_attempt

SVC_PREFIX = "https://content.lavote.gov/docs/rrcc/svc/"
HOSTS = {"lavote.gov", "www.lavote.gov", "results.lavote.gov", "content.lavote.gov"}
FOLLOW_WORDS = ("result", "svc", "statement", "historical", "election", "canvass", "archive")
SKIP_SUFFIXES = (".pdf", ".zip", ".xlsx", ".xls", ".csv", ".png", ".jpg", ".gif", ".css", ".js", ".ico", ".svg")
MAX_PAGES = 40
USER_AGENT = "la-county-elections-collector (public research project)"


def candidate_urls(election_id):
    """Likely names. Patterns seen: <id>_final_svc_<kind>[_public|_v2|_v3], <id>_svc_<kind>_zbc (excluded: zero-ballot report)."""
    out = []
    for kind in ("precinct", "countywide", "district"):
        for stage in ("final", "semifinal", "semi_final", ""):
            for suffix in ("", "_public", "_v2", "_v3", "_v4"):
                out.append(f"{SVC_PREFIX}{election_id}_{stage + '_' if stage else ''}svc_{kind}{suffix}.pdf")
    return out


def acceptable(url, election_id):
    """Only a precinct report of this election, never a zero-ballot (zbc) file."""
    return bool(re.fullmatch(rf"{re.escape(SVC_PREFIX)}{election_id}_[A-Za-z0-9_]*precinct[A-Za-z0-9_]*\.pdf", url)) and "zbc" not in url.lower()


def harvest(get_text, seeds, max_pages=MAX_PAGES, max_depth=2):
    """(sorted SVC pdf links found, pages fetched). Breadth-first over county pages only. get_text(url) -> html or None."""
    seen, queue, links, fetched = set(), [(s, 0) for s in seeds], set(), 0
    while queue and fetched < max_pages:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        html = get_text(url)
        fetched += 1
        if html is None:
            continue
        for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
            full = urllib.parse.urljoin(url, href.split("#")[0])
            p = urllib.parse.urlparse(full)
            if p.scheme not in ("http", "https") or p.netloc.lower() not in HOSTS:
                continue
            if "/docs/rrcc/svc/" in p.path and p.path.lower().endswith(".pdf"):
                links.add(f"https://{p.netloc.lower()}{p.path}")
            elif depth < max_depth and any(w in full.lower() for w in FOLLOW_WORDS) and not p.path.lower().endswith(SKIP_SUFFIXES):
                queue.append((full, depth + 1))
    return sorted(links), fetched


def get_text(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            if "html" not in (resp.headers.get("Content-Type") or "").lower():
                return None
            return resp.read(3_000_000).decode("utf-8", "replace")
    except Exception:
        return None


def head(url):
    """A probe entry in the same shape the collector logs (see tools.svc_auto.decide)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"result": "probed", "http_status": resp.status, "content_type": resp.headers.get("Content-Type", ""),
                    "content_length": resp.headers.get("Content-Length"), "last_modified": resp.headers.get("Last-Modified")}
    except urllib.error.HTTPError as e:
        return {"result": "error", "http_status": e.code}
    except Exception as e:
        return {"result": "error", "http_status": None, "error": type(e).__name__}


def run(election_id, seeds, flagged_urls, state_path, discovered_path, out_root, get=get_text, probe=head, now=None):
    """Returns the URLs to start. Writes discovered.json and updates the state file."""
    now = now or datetime.now(timezone.utc)
    harvested, pages = harvest(get, seeds)
    to_probe = sorted({u for u in harvested if u.startswith(SVC_PREFIX)} | set(candidate_urls(election_id)))
    found = {}
    for u in to_probe:
        e = probe(u)
        if e.get("http_status") == 200:
            found[u] = e
    sp = Path(state_path)
    state = json.loads(sp.read_text()) if sp.exists() else {}
    start = []
    for u in sorted(found):
        if u in flagged_urls or not acceptable(u, election_id):
            continue
        go, why = decide(found[u], u, state, now, out_root)
        print(f"{u}: {'START' if go else 'no'} - {why}")
        if go:
            record_attempt(state, u, found[u], now)
            start.append(u)
    dp = Path(discovered_path)
    prior = json.loads(dp.read_text()) if dp.exists() else {}
    first_seen = prior.get("first_seen", {})
    for u in found:
        first_seen.setdefault(u, now.isoformat())
    report = {"checked_at": now.isoformat(), "election_id": election_id, "pages_fetched": pages, "svc_links_on_county_pages": harvested,
              "urls_probed": len(to_probe), "found_200": {u: {k: e.get(k) for k in ("content_type", "content_length", "last_modified")} for u, e in found.items()},
              "first_seen": first_seen, "started_now": start}
    dp.parent.mkdir(parents=True, exist_ok=True)
    dp.write_text(json.dumps(report, indent=1) + "\n")
    if start:
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(state, indent=2) + "\n")
    print(f"pages fetched: {pages}; svc links on county pages: {len(harvested)}; probed: {len(to_probe)}; reachable: {len(found)}; to start: {len(start)}")
    return start


if __name__ == "__main__":
    election = sys.argv[1] if len(sys.argv) > 1 else "2026-11-03-general"
    config = json.loads(Path("config/sources.json").read_text())
    election_id = json.loads(Path(f"data/tidy/{election}/election.json").read_text())["election_id"]
    flagged = {s["url"] for s in config["sources"] if s.get("auto_svc")}
    urls = run(election_id, config.get("svc_discovery", {}).get("seed_pages", []), flagged,
               "data/svc_auto/discover_state.json", "data/svc_auto/discovered.json", "data/rehearsal")
    if len(sys.argv) > 2:  # GITHUB_OUTPUT
        with open(sys.argv[2], "a") as f:
            f.write(f"urls={' '.join(urls)}\nany={'true' if urls else 'false'}\n")
