from . import Adapter


def _sessions():
    from .. import sessions
    return sessions._copilot_sessions()


ADAPTER = Adapter(
    kind="copilot", name="GitHub Copilot", cls="AI agent", order=40,
    ancestry=r"(?i)copilot(-agent|-cli)?",
    env=("COPILOT_AGENT_ID", "GITHUB_COPILOT_SESSION"),
    sessions=_sessions,
)
