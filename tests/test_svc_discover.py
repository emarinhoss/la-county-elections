import json
from datetime import datetime, timedelta, timezone

from tools.svc_discover import SVC_PREFIX, acceptable, candidate_urls, harvest, run

NOW = datetime(2026, 12, 3, 12, 0, tzinfo=timezone.utc)
GUESS = f"{SVC_PREFIX}4348_final_svc_precinct_public.pdf"  # the name fetch.yml already watches


def pdf(length="61000000", ctype="application/pdf"):
    return {"result": "probed", "http_status": 200, "content_type": ctype, "content_length": length, "last_modified": "Thu, 03 Dec 2026 07:00:00 GMT"}


def test_generated_names_cover_every_real_county_name_we_have_seen():
    seen = ["4324_final_svc_precinct_public", "4324_final_svc_countywide", "4324_final_svc_district_v3", "4300_final_svc_countywide",
            "4306_final_svc_precinct_public"]
    for name in seen:
        election_id = name.split("_")[0]
        assert f"{SVC_PREFIX}{name}.pdf" in candidate_urls(election_id), name
    assert not any("zbc" in u for u in candidate_urls(4348))  # 4291_svc_precinct_zbc is a different kind of file


def test_only_a_precinct_report_of_this_election_is_acceptable():
    assert acceptable(f"{SVC_PREFIX}4348_final_svc_precinct_public.pdf", 4348)
    assert acceptable(f"{SVC_PREFIX}4348_semifinal_svc_precinct_v2.pdf", 4348)
    for bad in [f"{SVC_PREFIX}4324_final_svc_precinct_public.pdf",      # another election
                f"{SVC_PREFIX}4348_final_svc_countywide.pdf",           # not the precinct report
                f"{SVC_PREFIX}4348_svc_precinct_zbc.pdf",               # zero-ballot report
                f"{SVC_PREFIX}4348_final_svc_precinct.pdf?x=1",
                "https://example.com/docs/rrcc/svc/4348_final_svc_precinct.pdf"]:
        assert not acceptable(bad, 4348), bad


def test_harvest_follows_county_links_only_and_collects_svc_pdfs():
    pages = {
        "https://lavote.gov/start": '<a href="/election-results">r</a> <a href="https://evil.example/election-results">x</a> '
                                    '<a href="https://content.lavote.gov/docs/rrcc/svc/4348_x_svc_precinct_v9.pdf">p</a> '
                                    '<a href="/docs/other/4348.pdf">o</a> <a href="/about-us/background">a</a>',
        "https://lavote.gov/election-results": '<a href="/docs/rrcc/svc/4348_y_svc_precinct.pdf">q</a> <a href="/statement-of-votes">s</a>',
        "https://lavote.gov/statement-of-votes": '<a href="https://content.lavote.gov/docs/rrcc/svc/4348_z_svc_precinct.pdf#page=2">z</a>',
    }
    fetched = []

    def get(url):
        fetched.append(url)
        return pages.get(url)
    links, n = harvest(get, ["https://lavote.gov/start"])
    assert links == ["https://content.lavote.gov/docs/rrcc/svc/4348_x_svc_precinct_v9.pdf",
                     "https://content.lavote.gov/docs/rrcc/svc/4348_z_svc_precinct.pdf",
                     "https://lavote.gov/docs/rrcc/svc/4348_y_svc_precinct.pdf"]
    assert "https://evil.example/election-results" not in fetched and "https://lavote.gov/about-us/background" not in fetched
    assert n == 3


def test_harvest_stops_at_the_page_limit():
    def get(url):
        return "".join(f'<a href="/result{i}-{len(url)}">n</a>' for i in range(5))  # every page links to more pages forever
    _, n = harvest(get, ["https://lavote.gov/result"], max_pages=7)
    assert n == 7


def run_it(tmp_path, probe, get=lambda u: None, now=NOW, flagged=frozenset({GUESS})):
    return run(4348, ["https://lavote.gov/start"], flagged, tmp_path / "s.json", tmp_path / "d.json", tmp_path / "out", get=get, probe=probe, now=now)


def test_an_unexpected_file_name_found_on_a_county_page_is_started_once(tmp_path):
    odd = f"{SVC_PREFIX}4348_final_svc_precinct_v9.pdf"
    page = {"https://lavote.gov/start": f'<a href="{odd}">precinct</a>'}
    reachable = {odd: pdf(), GUESS: pdf(),                                       # GUESS is watched by fetch.yml: skipped here
                 f"{SVC_PREFIX}4348_svc_precinct_zbc.pdf": pdf(),                # zero-ballot report: never
                 f"{SVC_PREFIX}4348_final_svc_countywide.pdf": pdf()}            # found, but not the precinct report

    def probe(u):
        return reachable.get(u, {"result": "error", "http_status": 400})
    assert run_it(tmp_path, probe, page.get) == [odd]
    report = json.loads((tmp_path / "d.json").read_text())
    assert odd in report["found_200"] and f"{SVC_PREFIX}4348_final_svc_countywide.pdf" in report["found_200"]
    assert report["svc_links_on_county_pages"] == [odd] and report["started_now"] == [odd]
    # its run produced no output and a day has passed: one of the limited retries is allowed
    assert run_it(tmp_path, probe, page.get, now=NOW + timedelta(hours=24)) == [odd]
    report = json.loads((tmp_path / "d.json").read_text())
    assert report["first_seen"][odd] == NOW.isoformat()  # first-seen time is kept across days


def test_the_same_version_is_not_started_again_while_its_run_is_cooling_down(tmp_path):
    name = f"{SVC_PREFIX}4348_semifinal_svc_precinct_v2.pdf"
    probe = lambda u: pdf() if u == name else {"result": "error", "http_status": 404}
    assert run_it(tmp_path, probe) == [name]
    assert run_it(tmp_path, probe, now=NOW + timedelta(minutes=10)) == []


def test_nothing_is_started_for_a_stub_or_an_unpublished_file(tmp_path):
    name = f"{SVC_PREFIX}4348_final_svc_precinct.pdf"
    assert run_it(tmp_path, lambda u: pdf(length="5000") if u == name else {"result": "error", "http_status": 400}) == []
    report = json.loads((tmp_path / "d.json").read_text())
    assert name in report["found_200"] and report["started_now"] == []  # reachable and recorded, but too small to be the report
    assert run_it(tmp_path, lambda u: {"result": "error", "http_status": 400}) == []
    assert json.loads((tmp_path / "d.json").read_text())["found_200"] == {}
    assert not (tmp_path / "s.json").exists()  # nothing was attempted, so no state is written
