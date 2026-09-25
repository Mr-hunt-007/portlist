"""`portlist report` writes one page that stands on its own and, redacted, gives
nothing away; the agent adapters are the one place agents are defined."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plcore import lifecycle, report  # noqa: E402
from plcore.adapters import ADAPTERS, Adapter  # noqa: E402

from test_stop import row  # noqa: E402


def page(**kw):
    rows = [row(cmdline="python3 -m http.server 8787 --token=abc123 postgres://app:hunter2@db/x"),
            row(3000, 4123, service="Next.js", project={"name": "storefront", "short": "~/code/storefront"},
                exposure={"level": "loopback", "label": "Localhost only", "addrs": ["127.0.0.1"], "verified": None},
                leftover={"likely": False, "reasons": []}, risk=12, risk_band="Info",
                starter={"name": "Claude Code", "ai": True, "alive": True}),
            row(5000, 380, service="AirPlay", quiet=True)]
    return report.build(rows, {"hostname": "devbox.local"}, {"os": {"pretty": "macOS 15"}}, {}, now=1790000000, **kw)


def test_the_page_stands_alone_and_leads_with_the_verdict():
    html = page()
    assert "<script" not in html and "http://" not in html.replace("http.server", "") and "https://" not in html
    assert "1 reachable from beyond this machine" in html and "What needs a look" in html
    assert "portlist kill 8787" in html and "AirPlay" not in html


def test_secrets_in_command_lines_are_masked():
    html = page()
    assert "abc123" not in html and "hunter2" not in html and "--token=***" in html


def test_redacted_gives_nothing_away():
    html = page(redact=True)
    for leak in ("devbox", "storefront", "data-export", "192.0.2.14", "~/code", "http.server 8787", "me,"):
        assert leak not in html, leak
    assert "this-machine" in html and "project-1" in html


def test_adapters_define_every_agent_once_and_in_order():
    kinds = [a.kind for a in ADAPTERS]
    assert len(kinds) == len(set(kinds))
    assert kinds.index("claude-code") < kinds.index("vscode")        # specific before generic
    assert [s[0] for s in lifecycle.STARTERS[:len(kinds)]] == [a.kind for a in ADAPTERS if a.ancestry]
    assert {a.kind for a in ADAPTERS if a.ai} == lifecycle.AI_KINDS
    for a in ADAPTERS:
        assert a.cls in ("AI agent", "AI editor", "editor")


def test_an_adapter_is_recognised_from_the_ancestry():
    chain = [{"pid": 1, "name": "launchd", "cmdline": "/sbin/launchd"},
             {"pid": 700, "name": "node", "cmdline": "node /opt/homebrew/bin/gemini"},
             {"pid": 900, "name": "npm", "cmdline": "npm run dev"}]
    st = lifecycle.starter({"pid": 901}, chain)
    assert st["kind"] == "gemini" and st["ai"] and st["name"] == "Gemini CLI"


def test_bad_adapter_class_is_refused():
    try:
        Adapter("x", "X", cls="robot")
    except ValueError:
        return
    assert False, "cls must be checked"
