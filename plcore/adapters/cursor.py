from . import Adapter


def _sessions():
    from .. import sessions
    return sessions._glob_sessions(sessions.CURSOR_CHAT, sessions.read_vscode, "cursor")


ADAPTER = Adapter(
    kind="cursor", name="Cursor", cls="AI editor", order=20,
    ancestry=r"(?i)/cursor(?:\.app|/|\s)|cursor helper|cursor-agent",
    env=("CURSOR_TRACE_ID", "CURSOR_AGENT", "CURSOR_SESSION_ID"),
    sessions=_sessions,
)
