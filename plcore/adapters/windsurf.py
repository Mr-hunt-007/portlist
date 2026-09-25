from . import Adapter

ADAPTER = Adapter(kind="windsurf", name="Windsurf", cls="AI editor", order=70,
                  ancestry=r"(?i)windsurf", env=("WINDSURF_SESSION_ID", "CODEIUM_API_KEY"))
