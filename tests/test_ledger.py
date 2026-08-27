"""The launch ledger, tested against the five ways it is supposed to be useful.

Run with:  python3 -m unittest discover -s tests -v
       or: python3 tests/test_ledger.py

No fixtures on disk and no network: each test points PORTLIST_DATA at a fresh
temporary directory, so these can run anywhere and cannot touch a real install.
"""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def row(port, cmdline, cwd, pid, starter=None, **kw):
    """A scan row with only the fields the ledger reads."""
    r = {"port": port, "pid": pid, "cmdline": cmdline, "cmd": cmdline.split()[0],
         "dir": cwd, "quiet": False, "service": kw.pop("service", None),
         "project": {"name": os.path.basename(cwd)} if cwd else None,
         "starter": starter, "git_root": kw.pop("git_root", cwd)}
    r.update(kw)
    return r


def claude(pid=6214, alive=True):
    return {"kind": "claude-code", "name": "a Claude Code session", "class": "AI agent",
            "pid": pid, "via": "environment", "ai": True, "alive": alive}


def cursor(pid=7000):
    return {"kind": "cursor", "name": "Cursor", "class": "AI editor", "pid": pid,
            "via": "ancestry", "ai": True, "alive": True}


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pb-ledger-")
        os.environ["PORTLIST_DATA"] = self.tmp
        from plcore import ledger
        ledger.forget()
        self.ledger = ledger

    def tearDown(self):
        self.ledger.forget()
        os.environ.pop("PORTLIST_DATA", None)


class TestAgentExits(LedgerCase):
    """1. Claude starts a server, Claude exits, the server stays. Attribution survives."""

    def test_attribution_survives_the_agent_exiting(self):
        t0 = time.time() - 7200
        r = row(8787, "node server.js", "/repo-A", 6214, claude())
        self.ledger.observe([r], now=t0)
        self.assertEqual(r["origin"]["live"]["kind"], "claude-code")
        self.assertTrue(r["origin"]["carries_context"])

        # Two hours later the agent is gone, but the process kept its
        # environment, so the live answer still stands.
        later = row(8787, "node server.js", "/repo-A", 6214, claude(alive=False))
        self.ledger.observe([later], now=t0 + 7200)
        o = later["origin"]
        self.assertTrue(o["carries_context"], "env still on the process")
        self.assertEqual(o["recorded"]["kind"], "claude-code")
        self.assertAlmostEqual(o["started_at"], t0, delta=1)
        self.assertEqual(o["first_pid"], 6214)
        self.assertEqual(self.ledger.phrase(o), "Started by a Claude Code session")


class TestRespawnWithoutContext(LedgerCase):
    """2. The server dies, a supervisor restarts it with no agent environment.
    The original attribution has to survive, and must not be dressed up as live."""

    def test_original_attribution_survives_a_respawn(self):
        t0 = time.time() - 7200
        self.ledger.observe([row(8787, "node server.js", "/repo-A", 6214, claude())],
                            now=t0)
        # gone
        self.ledger.observe([], now=t0 + 3600)
        # back, started by a supervisor that carries nothing
        back = row(8787, "node server.js", "/repo-A", 8421, None)
        self.ledger.observe([back], now=t0 + 3660)

        o = back["origin"]
        self.assertIsNone(o["live"], "the new process carries no agent context")
        self.assertFalse(o["carries_context"])
        self.assertEqual(o["recorded"]["kind"], "claude-code")
        self.assertEqual(o["first_pid"], 6214)
        self.assertEqual(o["current_pid"], 8421)
        self.assertEqual(o["respawns"], 1)
        self.assertEqual(self.ledger.phrase(o),
                         "Originally started by a Claude Code session")

    def test_respawn_count_climbs(self):
        t0 = time.time() - 9000
        self.ledger.observe([row(8787, "node server.js", "/repo-A", 1, claude())], now=t0)
        for i in range(3):
            self.ledger.observe([], now=t0 + 100 * (2 * i + 1))
            back = row(8787, "node server.js", "/repo-A", 100 + i, None)
            self.ledger.observe([back], now=t0 + 100 * (2 * i + 2))
        self.assertEqual(back["origin"]["respawns"], 3)


class TestSameCommandTwoProjects(LedgerCase):
    """3. The same command in two different projects stays two different services."""

    def test_projects_do_not_merge(self):
        t0 = time.time() - 600
        a = row(3000, "npm run dev", "/repo-A", 11, claude())
        b = row(3001, "npm run dev", "/repo-B", 22, cursor())
        self.ledger.observe([a, b], now=t0)
        self.assertNotEqual(a["origin"]["sig"], b["origin"]["sig"])
        self.assertEqual(a["origin"]["recorded"]["kind"], "claude-code")
        self.assertEqual(b["origin"]["recorded"]["kind"], "cursor")

        # Respawn both without context. Each must keep its own origin.
        self.ledger.observe([], now=t0 + 60)
        a2 = row(3000, "npm run dev", "/repo-A", 33, None)
        b2 = row(3001, "npm run dev", "/repo-B", 44, None)
        self.ledger.observe([a2, b2], now=t0 + 120)
        self.assertEqual(a2["origin"]["recorded"]["kind"], "claude-code")
        self.assertEqual(b2["origin"]["recorded"]["kind"], "cursor")


class TestConcurrentDuplicates(LedgerCase):
    """Two of the same command in one directory, running at once, are two
    services. `recipes.signature` normalises the port out on purpose, so without
    care they collide and the second looks like a respawn of the first."""

    def test_two_instances_stay_two(self):
        t0 = time.time() - 600
        a = row(8787, "python -m http.server 8787", "/repo-A", 111, claude(6214))
        b = row(8807, "python -m http.server 8807", "/repo-A", 222, cursor(7000))
        self.ledger.observe([a, b], now=t0)
        self.assertNotEqual(a["origin"]["sig"], b["origin"]["sig"])
        self.assertEqual(a["origin"]["respawns"], 0)
        self.assertEqual(b["origin"]["respawns"], 0, "not a respawn of the first")
        self.assertEqual(a["origin"]["first_pid"], 111)
        self.assertEqual(b["origin"]["first_pid"], 222)
        self.assertTrue(a["origin"]["port_scoped"])

    def test_each_instance_keeps_its_own_origin_across_a_respawn(self):
        t0 = time.time() - 600
        a = row(8787, "python -m http.server 8787", "/repo-A", 111, claude())
        b = row(8807, "python -m http.server 8807", "/repo-A", 222, cursor())
        self.ledger.observe([a, b], now=t0)
        self.ledger.observe([], now=t0 + 60)
        a2 = row(8787, "python -m http.server 8787", "/repo-A", 333, None)
        b2 = row(8807, "python -m http.server 8807", "/repo-A", 444, None)
        self.ledger.observe([a2, b2], now=t0 + 120)
        self.assertEqual(a2["origin"]["recorded"]["kind"], "claude-code")
        self.assertEqual(b2["origin"]["recorded"]["kind"], "cursor")


class TestPidChanges(LedgerCase):
    """4. The pid changes and nothing else does. Provenance still matches."""

    def test_pid_is_never_the_identity(self):
        t0 = time.time() - 300
        first = row(5173, "vite --host", "/repo-A", 900, claude())
        self.ledger.observe([first], now=t0)
        again = row(5173, "vite --host", "/repo-A", 4321, claude())
        self.ledger.observe([again], now=t0 + 30)
        o = again["origin"]
        self.assertEqual(o["first_pid"], 900)
        self.assertEqual(o["current_pid"], 4321)
        self.assertTrue(o["certain"])
        self.assertEqual(o["matched"], "signature")

    def test_a_moved_port_keeps_its_origin(self):
        """:3000 was taken, so it came back on :3001. Same service."""
        t0 = time.time() - 300
        self.ledger.observe([row(3000, "npm run dev", "/repo-A", 5, claude())], now=t0)
        moved = row(3001, "npm run dev", "/repo-A", 6, None)
        self.ledger.observe([moved], now=t0 + 30)
        self.assertEqual(moved["origin"]["recorded"]["kind"], "claude-code")


class TestAmbiguity(LedgerCase):
    """5. When more than one record could be it, say unknown rather than guess."""

    def test_two_candidates_produce_no_attribution(self):
        t0 = time.time() - 600
        # Same command, same git root, two different working directories.
        a = row(3000, "npm run dev", "/repo/a", 11, claude(), git_root="/repo")
        b = row(3001, "npm run dev", "/repo/b", 22, cursor(), git_root="/repo")
        self.ledger.observe([a, b], now=t0)
        self.ledger.observe([], now=t0 + 60)

        # Now it comes back from a third directory under the same root, with no
        # environment. Two records could be it; neither may be claimed.
        mystery = row(3000, "npm run dev", "/repo/c", 33, None, git_root="/repo")
        rec, how, certain = self.ledger.match(mystery)
        self.assertIsNone(rec)
        self.assertEqual(how, "ambiguous")
        self.assertFalse(certain)

        self.ledger.observe([mystery], now=t0 + 120)
        o = mystery["origin"]
        self.assertIsNone(o["recorded"], "must not adopt either candidate")
        self.assertEqual(self.ledger.phrase(o), "Not attributed")

    def test_unknown_stays_unknown(self):
        r = row(9999, "./mystery", "/tmp/nowhere", 1, None)
        self.ledger.observe([r], now=time.time())
        self.assertIsNone(r["origin"]["live"])
        self.assertIsNone(r["origin"]["recorded"])
        self.assertEqual(self.ledger.phrase(r["origin"]), "Not attributed")


class TestReaperIsNotContext(LedgerCase):
    """A process reparented to launchd has a starter and no context. The recorded
    origin must outrank it, or every orphan reads as "started by launchd"."""

    def test_launchd_does_not_beat_the_ledger(self):
        t0 = time.time() - 3600
        self.ledger.observe([row(45999, "python app.py", "/repo-A", 100, claude())],
                            now=t0)
        self.ledger.observe([], now=t0 + 60)
        reaped = {"kind": "launchd", "name": "launchd", "class": "service manager",
                  "pid": 1, "via": "ancestry", "ai": False}
        back = row(45999, "python app.py", "/repo-A", 200, reaped)
        self.ledger.observe([back], now=t0 + 120)
        o = back["origin"]
        self.assertFalse(o["carries_context"], "launchd is not context")
        self.assertEqual(self.ledger.phrase(o),
                         "Originally started by a Claude Code session")
        self.assertEqual(o["respawns"], 1)

    def test_launchd_is_still_reported_when_that_is_all_there_is(self):
        reaped = {"kind": "launchd", "name": "launchd", "class": "service manager",
                  "pid": 1, "via": "ancestry", "ai": False}
        r = row(631, "cupsd", "/", 30, reaped)
        self.ledger.observe([r], now=time.time())
        self.assertEqual(self.ledger.phrase(r["origin"]), "Started by launchd")


class TestObservedVersusInferred(LedgerCase):
    """The ledger's history starts at its first observation. A service that was
    already running the first time portlist looked has an origin inferred from
    what the process carries now, not one observed at launch, and the record has
    to say which it is."""

    def test_a_launch_seen_while_watching_is_observed(self):
        t0 = time.time() - 3600
        # something is already on file, so the ledger has been watching
        self.ledger.observe([row(1111, "old thing", "/x", 1, None,
                                 started=t0 - 100)], now=t0)
        fresh = row(3000, "npm run dev", "/repo-A", 22, claude(), started=t0 + 300)
        self.ledger.observe([fresh], now=t0 + 305)
        self.assertTrue(fresh["origin"]["observed"])
        self.assertAlmostEqual(fresh["origin"]["process_started_at"], t0 + 300, delta=1)

    def test_a_process_older_than_the_ledger_is_not_observed(self):
        t0 = time.time() - 3600
        # the very first thing this ledger ever sees, and it started long before
        old = row(8080, "python app.py", "/repo-A", 5, claude(),
                  started=t0 - 86400)
        self.ledger.observe([old], now=t0)
        o = old["origin"]
        self.assertFalse(o["observed"],
                         "it was already running the first time portlist looked")
        # The attribution is still real - the process carries it - but the
        # timestamp is the process's own, not a launch portlist saw.
        self.assertEqual(o["recorded"]["kind"], "claude-code")
        self.assertAlmostEqual(o["started_at"], t0 - 86400, delta=1)
        self.assertLess(o["started_at"], o["first_seen_at"])

    def test_watching_since_is_the_earliest_record(self):
        t0 = time.time() - 7200
        self.ledger.observe([row(1, "a", "/x", 1, None, started=t0)], now=t0)
        self.ledger.observe([row(2, "b", "/y", 2, None, started=t0 + 60)],
                            now=t0 + 3600)
        self.assertAlmostEqual(self.ledger.watching_since(), t0, delta=1)

    def test_an_empty_ledger_observes_nothing(self):
        r = row(3000, "npm run dev", "/repo-A", 1, claude(), started=time.time())
        self.ledger.observe([r], now=time.time())
        self.assertFalse(r["origin"]["observed"],
                         "the first scan of a fresh ledger observed no launches")


class TestDurability(LedgerCase):
    """The ledger has to survive portlist restarting, which is the whole point."""

    def test_survives_a_process_restart(self):
        t0 = time.time() - 3600
        self.ledger.observe([row(8080, "python app.py", "/repo-A", 77, claude())], now=t0)
        self.assertTrue(os.path.isfile(self.ledger.path()))

        # Drop every in-memory structure, the way a fresh process would start.
        self.ledger._mem = None
        self.ledger._by_sig = None

        back = row(8080, "python app.py", "/repo-A", 88, None)
        self.ledger.observe([back], now=t0 + 60)
        self.assertEqual(back["origin"]["recorded"]["kind"], "claude-code")
        self.assertEqual(back["origin"]["first_pid"], 77)

    def test_the_file_is_append_only(self):
        t0 = time.time() - 300
        self.ledger.observe([row(1234, "a b", "/x", 1, claude())], now=t0)
        with open(self.ledger.path()) as f:
            first = f.read()
        self.ledger.observe([], now=t0 + 10)
        self.ledger.observe([row(1234, "a b", "/x", 2, None)], now=t0 + 20)
        with open(self.ledger.path()) as f:
            second = f.read()
        self.assertTrue(second.startswith(first), "earlier lines must never change")
        kinds = [__import__("json").loads(l)["event"] for l in second.splitlines()]
        self.assertEqual(kinds, ["launch", "stop", "respawn"])

    def test_a_torn_last_line_does_not_lose_the_file(self):
        t0 = time.time() - 300
        self.ledger.observe([row(1234, "a b", "/x", 1, claude())], now=t0)
        with open(self.ledger.path(), "a") as f:
            f.write('{"event": "launch", "sig": "tr')      # power cut mid-write
        self.ledger._mem = None
        self.ledger._by_sig = None
        again = row(1234, "a b", "/x", 1, None)
        self.ledger.observe([again], now=t0 + 30)
        self.assertEqual(again["origin"]["recorded"]["kind"], "claude-code")


class TestNoPortInheritance(LedgerCase):
    """A stale process must not pick up a repo label from whatever owns the port
    now. This is the failure the three-state `is_proxy` exists to prevent."""

    def test_an_unreadable_process_is_not_a_container(self):
        from plcore import containers
        # No name match and no readable working directory: another user's
        # process, or one in a restricted path. Indistinguishable from a proxy
        # by directory alone, which is why the answer has to be None.
        stale = {"cmd": "node", "cmdline": "node server.js", "dir": ""}
        self.assertIsNone(containers.is_proxy(stale))
        self.assertTrue(containers.is_proxy(
            {"cmd": "com.docker.backend", "cmdline": "com.docker.backend", "dir": ""}))
        self.assertFalse(containers.is_proxy(
            {"cmd": "node", "cmdline": "node s.js", "dir": "/Users/me/repo-A"}))

    def test_unknown_origin_stays_unknown_next_to_a_container(self):
        """A container publishes :6379 and something unattributable also holds it.
        The unattributable one must not end up filed under the compose project."""
        t0 = time.time()
        proxy = row(6379, "com.docker.backend", "/", 500, None)
        proxy["container"] = {"id": "abc", "name": "shop-redis-1", "image": "redis:7",
                              "project": "shop", "service": "redis", "engine": "docker"}
        stale = row(6379, "node server.js", "", 900, None)
        stale["project"] = None            # its directory could not be read
        self.ledger.observe([proxy, stale], now=t0)
        self.assertEqual(proxy["origin"]["live"]["kind"], "compose")
        self.assertIsNone(stale["origin"]["live"],
                          "no container, so no compose starter")
        self.assertIsNone(stale["origin"]["recorded"])
        self.assertIsNone(stale["origin"]["project"],
                          "must not borrow the project from the port's container")
        self.assertEqual(self.ledger.phrase(stale["origin"]), "Not attributed")


class TestContainers(LedgerCase):
    """A compose project is a durable answer to "who started this", and beats
    "launchd ran the engine's proxy"."""

    def test_compose_is_the_starter(self):
        r = row(6379, "com.docker.backend", "/", 500, None)
        r["container"] = {"id": "abc", "name": "shop-redis-1", "image": "redis:7",
                          "project": "shop", "service": "redis", "engine": "docker"}
        self.ledger.observe([r], now=time.time())
        self.assertEqual(r["origin"]["live"]["kind"], "compose")
        self.assertTrue(r["origin"]["live_is_container"])
        self.assertEqual(self.ledger.phrase(r["origin"]),
                         "Started by Docker Compose (shop)")


class TestAttributionChange(LedgerCase):
    def test_a_changed_starter_is_recorded_not_overwritten(self):
        t0 = time.time() - 600
        self.ledger.observe([row(4000, "serve .", "/repo-A", 1, claude())], now=t0)
        self.ledger.observe([row(4000, "serve .", "/repo-A", 1, cursor())], now=t0 + 60)
        evs = [e["event"] for e in self.ledger.events()]
        self.assertIn("attribution", evs)
        rec = self.ledger.state()[0]
        self.assertEqual(rec["starter"]["kind"], "claude-code",
                         "the original launch record is never rewritten")


if __name__ == "__main__":
    unittest.main(verbosity=2)
