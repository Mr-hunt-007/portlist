"""The dashboard's numbers must count what is running.

`docker ps -a` lists the containers that have exited as well as the ones that
are up. The CONTAINERS card used to count all of them as running, and to count
the host ports the stopped ones no longer hold. A card that says five
containers are running when two are is the kind of confident wrong number this
project exists to avoid.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plcore import dash  # noqa: E402


class FakeTui:
    """Just enough of the Tui for the dashboard to draw its cards into."""

    class G:
        full = "#"
        empty = "-"
        tl = h = v = tr = bl = br = ""

    def __init__(self, containers=None, summary=None, groups=None, rows=None):
        self.sysinfo = {}
        self.summary = summary or {"shown": 3, "exposed": 1, "critical": 0, "high": 0}
        self.groups = groups or []
        self.containers = containers if containers is not None else {}
        self.rows = rows or []
        self.frame = 0
        self.anim = False
        self.g = self.G()
        self.cells = {}

    def put(self, y, x, text, pair=1, bold=False):
        self.cells[(y, x)] = text

    def box(self, y, x, h, w, title, pair=1, title_pair=None):
        return y + 1, x + 2, max(0, w - 4)

    def ease(self, key, target):
        return target


def container(cid, state, port=None, project=None):
    return {"id": cid, "name": "box-" + cid, "image": "img", "engine": "docker",
            "state": state, "project": project,
            "ports": [{"host_port": port, "proto": "tcp"}] if port else []}


def card_value(t, label):
    """-> the value drawn next to `label` in a card, or None."""
    for (y, x), text in t.cells.items():
        if text == label:
            return t.cells.get((y, x + 13))
    return None


def draw_cards(containers, width=100):
    t = FakeTui(containers=containers)
    dash._cards(t, 3, 30, width)
    return t


def test_the_container_card_counts_only_the_containers_that_are_up():
    doc = {"engine": "docker", "reachable": True, "running": 2, "total": 4,
           "containers": [
               container("a", "running", 6379, "shop"),
               container("b", "running", 8080, "shop"),
               container("c", "exited", 5432, "old"),
               container("d", "created", None, None)]}
    t = draw_cards(doc)
    assert card_value(t, "RUNNING") == "2"
    assert card_value(t, "HOST PORTS") == "2"


def test_a_stopped_container_publishes_no_port():
    doc = {"engine": "docker", "reachable": True, "running": 1, "total": 2,
           "containers": [
               container("a", "running", 6379, "shop"),
               container("b", "exited", 5432, "old")]}
    t = draw_cards(doc)
    assert card_value(t, "HOST PORTS") == "1"


def test_the_card_still_says_what_it_cannot_see():
    doc = {"engine": "docker", "reachable": False, "containers": []}
    t = draw_cards(doc)
    assert card_value(t, "COUNT") == "unknown"
    assert card_value(t, "ENGINE") == "docker"
