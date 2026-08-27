#!/usr/bin/env sh
# portlist installer.
#
#   curl -fsSL https://mr-hunt-007.github.io/portlist/install.sh | sh
#
# It installs to ~/.local/bin, needs nothing but Python 3.9+, and touches no
# system directory. Read it first - that is the point of shipping it readable.
set -eu

REPO="https://github.com/Mr-hunt-007/portlist"
PREFIX="${PORTLIST_PREFIX:-$HOME/.local}"
LIB="$PREFIX/lib/portlist"
BIN="$PREFIX/bin"

have() { command -v "$1" >/dev/null 2>&1; }

PY=""
for c in python3 python; do
  if have "$c" && "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || { echo "portlist needs Python 3.9 or newer on PATH." >&2; exit 1; }
"$PY" -c 'import curses' 2>/dev/null || {
  echo "This Python has no curses module, which portlist is built on." >&2
  echo "On Windows: pip install windows-curses. On Linux: install python3-curses." >&2
  exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM

echo "fetching portlist..."
if have curl; then
  curl -fsSL "$REPO/archive/refs/heads/main.tar.gz" -o "$TMP/src.tar.gz"
elif have wget; then
  wget -qO "$TMP/src.tar.gz" "$REPO/archive/refs/heads/main.tar.gz"
else
  echo "neither curl nor wget is available." >&2; exit 1
fi
tar -xzf "$TMP/src.tar.gz" -C "$TMP"
# GitHub names the directory portlist-main for a branch and portlist-1.1 for a
# tag; a hand-rolled tarball may just say portlist. Accept all three.
SRC="$(find "$TMP" -maxdepth 1 -type d -name 'portlist*' | head -1)"
[ -d "$SRC" ] || { echo "the download did not contain what was expected." >&2; exit 1; }

mkdir -p "$LIB" "$BIN"
rm -rf "$LIB/plcore" "$LIB/portlist.py"
cp -R "$SRC/plcore" "$SRC/portlist.py" "$LIB/"
cat > "$BIN/portlist" <<SH
#!/usr/bin/env sh
exec "$PY" "$LIB/portlist.py" "\$@"
SH
chmod +x "$BIN/portlist"

echo "installed: $BIN/portlist"
case ":$PATH:" in
  *":$BIN:"*) echo "run: portlist" ;;
  *) echo "note: $BIN is not on your PATH. Add it, or run $BIN/portlist" ;;
esac
