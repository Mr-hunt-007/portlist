from . import Adapter


def _sessions():
    from .. import sessions
    return sessions._glob_sessions(sessions.GEMINI_GLOBS, sessions.read_gemini)


# The CLI is a node script, so its own process shows up as `node .../gemini`:
# the ancestry pattern finds it by the script's name at the end of a path.
ADAPTER = Adapter(
    kind="gemini", name="Gemini CLI", cls="AI agent", order=74,
    ancestry=r"(?:^|/)gemini(?:\s|$)",
    sessions=_sessions,
)
