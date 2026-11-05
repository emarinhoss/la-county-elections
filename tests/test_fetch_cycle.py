"""Runs tools/fetch_cycle.sh for real against a local bare repository (the "origin") and a fake `gh` that records what it is asked to start."""
import json
import os
import shutil
import subprocess
import sys
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None, reason="needs bash and git")


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


class World:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.www = tmp_path / "www"
        self.www.mkdir()
        handler = type("Quiet", (SimpleHTTPRequestHandler,), {"log_message": lambda *a: None})
        self.server = HTTPServer(("127.0.0.1", 0), partial(handler, directory=str(self.www)))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.api = tmp_path / "counter.json"
        self.api.write_text(json.dumps({"TimeStamp": "t1", "Data": [{"id": 1, "v": 5}, {"id": 2, "v": 7}]}))
        self.pdf_url = f"http://127.0.0.1:{self.server.server_port}/4348_svc_precinct_public.pdf"

        self.origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        seed = tmp_path / "seed"
        seed.mkdir()
        for d in ("collect", "parse", "tools"):
            shutil.copytree(REPO / d, seed / d, ignore=shutil.ignore_patterns("__pycache__"))
        (seed / "config").mkdir()
        (seed / "config" / "sources.json").write_text(json.dumps({"election": "2026-11-03-general", "sources": [
            {"id": "rrcc_api_counter_data", "url": self.api.as_uri(), "canonical_json": True},
            {"id": "svc_2026_precinct_pdf", "url": self.pdf_url, "head": True, "auto_svc": True}]}))
        subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
        git(seed, "add", "-A")
        git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "seed")
        git(seed, "remote", "add", "origin", str(self.origin))
        git(seed, "push", "-q", "origin", "main")
        self.work = tmp_path / "work"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.work)], check=True)

        self.gh_log = tmp_path / "gh.log"
        self.gh_log.write_text("")
        (tmp_path / "bin").mkdir()
        fake = tmp_path / "bin" / "gh"
        fake.write_text('#!/usr/bin/env bash\necho "$@" >> "$GH_LOG"\n')
        fake.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "GH_LOG": str(self.gh_log), "GH_TOKEN": "x",
                    "PYTHON": sys.executable}

    def cycle(self, where=None):
        where = where or self.work
        r = subprocess.run(["bash", str(where / "tools" / "fetch_cycle.sh")], cwd=where, env=self.env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr  # a cycle never fails the job
        return r.stdout

    def origin_commits(self):
        return int(subprocess.run(["git", "--git-dir", str(self.origin), "rev-list", "--count", "main"], capture_output=True, text=True).stdout)

    def dispatched(self):
        return self.gh_log.read_text().splitlines()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.close()


def test_a_real_change_is_committed_and_the_site_rebuild_is_requested(world):
    base = world.origin_commits()
    out = world.cycle()
    assert "pushed" in out and world.origin_commits() == base + 1
    assert world.dispatched() == ["workflow run pages.yml --ref main"]  # a new county tally rebuilds the site
    assert (world.work / "data/raw/2026-11-03-general/fetch_log.jsonl").exists()


def test_a_cycle_where_only_the_attempt_log_changed_makes_no_commit_and_starts_nothing(world):
    world.cycle()
    commits, dispatches = world.origin_commits(), world.dispatched()
    out = world.cycle()
    assert "nothing new" in out and world.origin_commits() == commits and world.dispatched() == dispatches
    assert git(world.work, "rev-list", "--count", "origin/main..HEAD") == "0"  # nothing is left committed locally and unpushed
    world.cycle()
    assert world.origin_commits() == commits  # still nothing, and the staged log from the last cycle does not break the next one


def test_a_new_tally_is_committed_again_and_a_failing_parse_does_not_stop_collection(world):
    world.cycle()
    commits = world.origin_commits()
    world.api.write_text(json.dumps({"TimeStamp": "t2", "Data": [{"id": 1, "v": 6}, {"id": 2, "v": 7}]}))
    out = world.cycle()
    assert "WARNING: parse failed" in out  # this tiny repo has no election data to parse: collection still goes on
    assert world.origin_commits() == commits + 1 and world.dispatched().count("workflow run pages.yml --ref main") == 2


def test_it_recovers_when_someone_else_pushed_in_between(world):
    world.cycle()
    other = world.tmp / "other"
    subprocess.run(["git", "clone", "-q", str(world.origin), str(other)], check=True)
    (other / "note.txt").write_text("another workflow committed this\n")
    git(other, "add", "-A")
    git(other, "-c", "user.name=o", "-c", "user.email=o@o", "commit", "-q", "-m", "other")
    git(other, "push", "-q", "origin", "main")
    world.api.write_text(json.dumps({"TimeStamp": "t3", "Data": [{"id": 1, "v": 9}]}))
    world.cycle()
    log = subprocess.run(["git", "--git-dir", str(world.origin), "log", "--format=%s", "main"], capture_output=True, text=True).stdout.splitlines()
    assert "other" in log and sum(1 for m in log if m.startswith("data: new snapshots")) == 2  # both survived


def test_the_svc_pipeline_is_started_once_when_the_file_appears(world):
    world.cycle()
    assert not any("svc-rehearsal" in line for line in world.dispatched())  # not published: the probe sees a 404
    (world.www / "4348_svc_precinct_public.pdf").write_bytes(b"%PDF-1.4\n" + b"0" * 1_500_000)
    out = world.cycle()
    started = [line for line in world.dispatched() if "svc-rehearsal" in line]
    assert started == [f"workflow run svc-rehearsal.yml -f url={world.pdf_url} --ref main"] and "starting the pipeline" in out
    state = json.loads(git(world.work, "show", "origin/main:data/svc_auto/state.json"))  # the attempt is recorded in the repo
    assert state[world.pdf_url]["attempts"] == 1
    world.cycle()
    assert [line for line in world.dispatched() if "svc-rehearsal" in line] == started  # the next cycle does not start it again


def test_a_tally_that_another_workflow_already_saved_is_not_saved_twice(world):
    other = world.tmp / "other2"  # the scheduled run and the poller are two clones of the same repository
    subprocess.run(["git", "clone", "-q", str(world.origin), str(other)], check=True)
    world.cycle(where=other)  # the other one saves and pushes this tally first
    commits = world.origin_commits()
    out = world.cycle()  # our cycle must start from what is published, see that snapshot, and add nothing
    assert "nothing new" in out and world.origin_commits() == commits
    snapshots = list((world.work / "data/raw/2026-11-03-general/rrcc_api_counter_data").iterdir())
    assert len(snapshots) == 1
