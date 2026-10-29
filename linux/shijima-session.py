#!/usr/bin/env python3
"""Start Shijima-Qt and reconcile the AvA crew to one of each, under a lock.

Only the four named AvA mascots are managed. Other imported/on-screen mascots
are left alone. An unreadable API response must NEVER be treated as an empty
screen: that would add another four at every login/retry.
"""
import collections
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:32456/shijima/api/v1"
WANT = ("Blue", "Orange", "Yellow", "Green")
SPAWN_STAGGER_SECONDS = 0.18      # do not seed all four on the same host tick


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    # This is a local desktop API, not a remote service or an HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=4) as resp:
        return json.loads(resp.read().decode() or "{}")


def on_screen():
    data = call("GET", "/mascots")
    if not isinstance(data, dict) or not isinstance(data.get("mascots"), list):
        raise ValueError("invalid GET /mascots response; refusing to spawn duplicates")
    mascots = data["mascots"]
    ids = set()
    for m in mascots:
        if (not isinstance(m, dict) or not isinstance(m.get("name"), str)
                or type(m.get("id")) is not int or m["id"] < 0 or m["id"] in ids):
            raise ValueError("invalid mascot entry; refusing to change the screen")
        ids.add(m["id"])
    return mascots


def reconcile(mascots):
    seen = collections.defaultdict(list)
    for mascot in mascots:
        if mascot["name"] in WANT:
            seen[mascot["name"]].append(mascot["id"])
    missing = [name for name in WANT if not seen[name]]
    for name in WANT:
        # Clean up an existing crowd, not just prevent another one next login.
        for mascot_id in seen[name][1:]:
            call("DELETE", f"/mascots/{mascot_id}")
    for index, name in enumerate(missing):
        call("POST", "/mascots", {"name": name})
        if index + 1 < len(missing):
            time.sleep(SPAWN_STAGGER_SECONDS)


def start(launcher):
    try:
        mascots = on_screen()
    except urllib.error.HTTPError:
        # A responding server with an error is not a missing application.
        raise
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        cache = Path((os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")))
        cache.mkdir(parents=True, exist_ok=True)
        log = cache / "ava-shijima.log"
        env = dict(os.environ, QT_QPA_PLATFORM="xcb")
        with log.open("ab") as output:
            subprocess.Popen(launcher, env=env, stdin=subprocess.DEVNULL,
                             stdout=output, stderr=subprocess.STDOUT,
                             start_new_session=True, close_fds=True)
        deadline = time.monotonic() + 90
        while True:
            try:
                mascots = on_screen()
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Shijima-Qt API never answered; see {log}") from exc
                time.sleep(2)
    reconcile(mascots)


def main(argv=None):
    launcher = list(sys.argv[1:] if argv is None else argv)
    if launcher[:1] == ["--"]:
        launcher.pop(0)
    if not launcher:
        sys.exit("Usage: shijima-session.py -- shijima-qt (or flatpak run APP_ID)")
    cache = (os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache"))
    state = Path((os.environ.get("XDG_RUNTIME_DIR") or cache)) / "ava-shimeji"
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state / "shijima-session.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        try:
            start(launcher)
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"ava-shijima: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
