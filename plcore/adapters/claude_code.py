from . import Adapter


def _sessions():
    from .. import sessions
    return sessions.claude_files()


ADAPTER = Adapter(
    kind="claude-code", name="Claude Code", cls="AI agent", order=10,
    ancestry=r"(?:^|/)claude(?:\s|$)|claude-code|\bclaude\.js\b",
    env=("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID"),
    processes=("claude",),
    sessions=_sessions,
)
