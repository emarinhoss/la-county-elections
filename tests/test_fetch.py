import json

from collect.fetch import run


def make_config(tmp_path, files):
    sources = []
    for name, text in files.items():
        p = tmp_path / name
        p.write_text(text)
        sources.append({"id": name, "url": p.as_uri()})
    cfg = tmp_path / "sources.json"
    cfg.write_text(json.dumps({"election": "test", "sources": sources}))
    return cfg


def results(entries):
    return {e["source_id"]: e["result"] for e in entries}


def test_saves_then_skips_unchanged_then_saves_change(tmp_path):
    cfg = make_config(tmp_path, {"a": "one"})
    root = tmp_path / "raw"
    assert results(run(cfg, root)) == {"a": "saved"}
    assert results(run(cfg, root)) == {"a": "unchanged"}
    (tmp_path / "a").write_text("two")
    assert results(run(cfg, root)) == {"a": "saved"}
    snaps = list((root / "test" / "a").iterdir())
    assert len(snaps) == 2


def test_manifest_has_hash_and_body_matches(tmp_path):
    cfg = make_config(tmp_path, {"a": "hello"})
    root = tmp_path / "raw"
    run(cfg, root)
    snap = next((root / "test" / "a").iterdir())
    manifest = json.loads((snap / "manifest.json").read_text())
    assert (snap / "body").read_bytes() == b"hello"
    assert manifest["bytes"] == 5
    assert len(manifest["sha256"]) == 64


def test_one_failure_does_not_block_others_and_is_logged(tmp_path):
    cfg = make_config(tmp_path, {"good": "x"})
    conf = json.loads(cfg.read_text())
    conf["sources"].append({"id": "bad", "url": (tmp_path / "missing").as_uri()})
    cfg.write_text(json.dumps(conf))
    root = tmp_path / "raw"
    assert results(run(cfg, root)) == {"good": "saved", "bad": "error"}
    log = (root / "test" / "fetch_log.jsonl").read_text().splitlines()
    assert len(log) == 2
    assert not (root / "test" / "bad").exists()


# ---- probe mode, size cap, HTTP errors (use a real local HTTP server) ----
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler


def serve(directory):
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = HTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def run_one(tmp_path, source):
    cfg = tmp_path / "s.json"
    cfg.write_text(json.dumps({"election": "t", "sources": [source]}))
    return run(cfg, tmp_path / "raw")[0]


def test_probe_records_size_but_stores_nothing(tmp_path):
    (tmp_path / "www").mkdir()
    (tmp_path / "www" / "big.pdf").write_bytes(b"x" * 1000)
    server, base = serve(tmp_path / "www")
    entry = run_one(tmp_path, {"id": "p", "url": base + "/big.pdf", "head": True})
    server.shutdown()
    assert entry["result"] == "probed" and entry["http_status"] == 200 and entry["content_length"] == "1000"
    assert not (tmp_path / "raw" / "t" / "p").exists()


def test_http_404_is_logged_with_its_status(tmp_path):
    (tmp_path / "www").mkdir()
    server, base = serve(tmp_path / "www")
    entry = run_one(tmp_path, {"id": "p", "url": base + "/missing.pdf", "head": True})
    server.shutdown()
    assert entry["result"] == "error" and entry["http_status"] == 404


def test_file_over_size_cap_is_not_saved(tmp_path):
    (tmp_path / "www").mkdir()
    (tmp_path / "www" / "f").write_bytes(b"x" * 500)
    server, base = serve(tmp_path / "www")
    entry = run_one(tmp_path, {"id": "p", "url": base + "/f", "max_bytes": 100})
    server.shutdown()
    assert entry["result"] == "too_large"
    assert not (tmp_path / "raw" / "t" / "p").exists()


# ---- canonical JSON: the county API reorders rows between requests ----
def test_same_rows_in_a_different_order_is_unchanged_but_a_new_value_is_saved(tmp_path):
    src = tmp_path / "api.json"
    cfg = tmp_path / "s.json"
    cfg.write_text(json.dumps({"election": "t", "sources": [{"id": "api", "url": src.as_uri(), "canonical_json": True}]}))
    root = tmp_path / "raw"
    src.write_text(json.dumps({"TimeStamp": "t1", "Data": [{"id": 1, "v": 5}, {"id": 2, "v": 7}]}))
    assert results(run(cfg, root)) == {"api": "saved"}
    src.write_text(json.dumps({"TimeStamp": "t1", "Data": [{"id": 2, "v": 7}, {"id": 1, "v": 5}]}))  # same rows, reordered
    assert results(run(cfg, root)) == {"api": "unchanged"}
    src.write_text(json.dumps({"TimeStamp": "t1", "Data": [{"id": 2, "v": 8}, {"id": 1, "v": 5}]}))  # one value changed
    assert results(run(cfg, root)) == {"api": "saved"}
    assert len(list((root / "t" / "api").iterdir())) == 2


def test_without_the_flag_a_reordered_file_still_counts_as_changed(tmp_path):
    src = tmp_path / "api.json"
    cfg = tmp_path / "s.json"
    cfg.write_text(json.dumps({"election": "t", "sources": [{"id": "api", "url": src.as_uri()}]}))
    root = tmp_path / "raw"
    src.write_text('{"Data":[1,2]}')
    run(cfg, root)
    src.write_text('{"Data":[2,1]}')
    assert results(run(cfg, root)) == {"api": "saved"}


def test_ignored_key_does_not_cause_a_new_snapshot_but_other_changes_do(tmp_path):
    src = tmp_path / "api.json"
    cfg = tmp_path / "s.json"
    cfg.write_text(json.dumps({"election": "t", "sources": [
        {"id": "api", "url": src.as_uri(), "canonical_json": True, "ignore_keys": ["TimeStamp"]}]}))
    root = tmp_path / "raw"
    src.write_text(json.dumps({"TimeStamp": "9:59", "Data": [1, 2]}))
    assert results(run(cfg, root)) == {"api": "saved"}
    src.write_text(json.dumps({"TimeStamp": "10:10", "Data": [2, 1]}))  # only the stamp (and row order) changed
    assert results(run(cfg, root)) == {"api": "unchanged"}
    src.write_text(json.dumps({"TimeStamp": "10:20", "Data": [1, 2, 3]}))
    assert results(run(cfg, root)) == {"api": "saved"}
