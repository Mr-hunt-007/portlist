"""Pick a backend for the running OS."""
import platform

SYSTEM = platform.system()

if SYSTEM == "Darwin":
    from . import darwin as impl
elif SYSTEM == "Linux":
    from . import linux as impl
elif SYSTEM == "Windows":
    from . import windows as impl
else:                                    # FreeBSD and friends: lsof/ps are close enough
    from . import darwin as impl

NAME = {"Darwin": "macOS", "Linux": "Linux", "Windows": "Windows"}.get(SYSTEM, SYSTEM)

# Backends verified against real hardware by the author. Unverified backends
# still run; the UI labels the platform so nobody mistakes "no data" for "no risk".
VERIFIED = SYSTEM == "Darwin"
