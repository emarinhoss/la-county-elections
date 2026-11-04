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
