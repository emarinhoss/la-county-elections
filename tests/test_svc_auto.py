import json
from datetime import datetime, timedelta, timezone

from tools.svc_auto import MAX_ATTEMPTS, decide, latest_probe, record_attempt, run

URL = "https://content.lavote.gov/docs/rrcc/svc/4348_final_svc_precinct_public.pdf"
NOW = datetime(2026, 12, 3, 12, 0, tzinfo=timezone.utc)


def probe(status=200, ctype="application/pdf", length="61021444", modified="Thu, 03 Dec 2026 07:00:00 GMT", result="probed"):
    return {"source_id": "svc_2026_precinct_pdf", "result": result, "http_status": status, "content_type": ctype,
            "content_length": length, "last_modified": modified}


def test_nothing_happens_until_the_file_is_really_there(tmp_path):
    assert decide(None, URL, {}, NOW, tmp_path)[0] is False
    assert decide(probe(status=400, result="error"), URL, {}, NOW, tmp_path)[0] is False  # what the county returns today
    assert decide(probe(status=404, result="error"), URL, {}, NOW, tmp_path)[0] is False
    assert decide(probe(ctype="text/html"), URL, {}, NOW, tmp_path)[0] is False            # an error page served with 200
    assert decide(probe(length="5000"), URL, {}, NOW, tmp_path)[0] is False               # a stub, not a 60 MB report
    go, why = decide(probe(), URL, {}, NOW, tmp_path)
    assert go is True and "new" in why


def test_a_version_is_processed_once_and_a_changed_version_again(tmp_path):
    state = {}
    record_attempt(state, URL, probe(), NOW)
    out = tmp_path / "4348_final_svc_precinct_public"
    out.mkdir()
    (out / "countywide_checks.csv").write_text("seq\n")
    assert decide(probe(), URL, state, NOW + timedelta(hours=5), tmp_path) == (False, "this version was already processed")
    go, why = decide(probe(length="62000000"), URL, state, NOW + timedelta(hours=5), tmp_path)  # the county replaced the file
    assert go is True and why == "new or changed file"


def test_a_failed_run_is_retried_a_limited_number_of_times_with_a_cooldown(tmp_path):
    state = {}
    t = NOW
    record_attempt(state, URL, probe(), t)  # attempt 1, and no output was ever produced
    assert decide(probe(), URL, state, t + timedelta(minutes=30), tmp_path)[0] is False  # cooling down
    for attempt in range(2, MAX_ATTEMPTS + 1):
        t += timedelta(minutes=61)
        go, why = decide(probe(), URL, state, t, tmp_path)
        assert go is True and f"attempt {attempt}" in why
        record_attempt(state, URL, probe(), t)
    t += timedelta(hours=24)
    go, why = decide(probe(), URL, state, t, tmp_path)
    assert go is False and "gave up" in why
    assert decide(probe(modified="Fri, 04 Dec 2026 07:00:00 GMT"), URL, state, t, tmp_path)[0] is True  # a changed file starts over


def test_latest_probe_takes_the_newest_log_line():
    lines = [json.dumps({**probe(status=400, result="error")}), "", json.dumps(probe()), json.dumps({"source_id": "other"})]
    assert latest_probe(lines, "svc_2026_precinct_pdf")["http_status"] == 200
    assert latest_probe(lines, "nope") is None


def test_run_only_looks_at_flagged_sources_and_remembers_the_attempt(tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"sources": [
        {"id": "svc_2026_precinct_pdf", "url": URL, "auto_svc": True},
        {"id": "svc_2024_precinct_pdf", "url": "https://content.lavote.gov/docs/rrcc/svc/4324_final_svc_precinct_public.pdf"}]}))
    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps(probe()) + "\n" + json.dumps({**probe(), "source_id": "svc_2024_precinct_pdf"}) + "\n")
    state = tmp_path / "state" / "s.json"
    assert run(cfg, log, state, tmp_path / "out", NOW) == [URL]  # the 2024 probe is 200 too but is not flagged
    assert json.loads(state.read_text())[URL]["attempts"] == 1
    assert run(cfg, log, state, tmp_path / "out", NOW + timedelta(minutes=5)) == []  # same version, just tried
