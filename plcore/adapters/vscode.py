from . import Adapter


def _sessions():
    from .. import sessions
    return sessions._glob_sessions(sessions.VSCODE_CHAT, sessions.read_vscode, "vscode")


# After every AI editor: most of them are forks of VS Code and their helpers
# would otherwise match the generic `code` pattern first.
ADAPTER = Adapter(
    kind="vscode", name="VS Code", cls="editor", order=90,
    ancestry=r"(?i)visual studio code|/code helper|(?:^|/)code(?:\s|$)|electron.*vscode",
    env=("VSCODE_GIT_ASKPASS_NODE", "VSCODE_PID", "VSCODE_CWD"),
    sessions=_sessions,
)
