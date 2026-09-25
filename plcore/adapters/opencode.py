from . import Adapter

ADAPTER = Adapter(kind="opencode", name="OpenCode", cls="AI agent", order=76,
                  ancestry=r"(?:^|/)opencode(?:\s|$)", processes=("opencode",))
