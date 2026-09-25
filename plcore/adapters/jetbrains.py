from . import Adapter

ADAPTER = Adapter(kind="jetbrains", name="JetBrains IDE", cls="editor", order=95,
                  ancestry=r"(?i)(intellij|pycharm|webstorm|goland|rubymine|jetbrains)",
                  env=("IDEA_INITIAL_DIRECTORY", "PYCHARM_HOSTED"))
