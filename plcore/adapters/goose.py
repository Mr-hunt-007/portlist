from . import Adapter

ADAPTER = Adapter(kind="goose", name="Goose", cls="AI agent", order=60,
                  ancestry=r"(?:^|/)goose(?:\s|$)", processes=("goose",))
