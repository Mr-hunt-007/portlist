from . import Adapter


def _sessions():
    from .. import sessions
    return sessions.codex_files()


ADAPTER = Adapter(
    kind="codex", name="Codex CLI", cls="AI agent", order=30,
    ancestry=r"(?:^|/)codex(?:\s|$)|codex-cli",
    env=("CODEX_SANDBOX", "CODEX_HOME", "CODEX_SESSION_ID"),
    processes=("codex",),
    sessions=_sessions,
)
