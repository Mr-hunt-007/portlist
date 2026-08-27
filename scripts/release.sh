#!/usr/bin/env bash
# Cut a release: build the artifacts, then stamp their real checksums into the
# Homebrew formula and the winget manifest.
#
#   scripts/release.sh 1.1
#
# A placeholder checksum that ships is worse than no formula at all: it fails
# the install with a message that reads like a compromised download. This script
# exists so that never has to be done by hand.
set -euo pipefail

VERSION="${1:-}"
[ -n "$VERSION" ] || { echo "usage: scripts/release.sh <version>" >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist"
cd "$ROOT"

grep -q "\"$VERSION\"" pyproject.toml || {
  echo "pyproject.toml is not at $VERSION - bump it first" >&2; exit 2; }
grep -q "VERSION = \"$VERSION\"" plcore/app.py || {
  echo "plcore/app.py is not at $VERSION - bump it first" >&2; exit 2; }

rm -rf "$OUT"; mkdir -p "$OUT"

# 1. the Windows zip: source plus a shim, laid out the way the winget manifest
#    says it is (portlist-<version>/portlist.cmd).
STAGE="$OUT/portlist-$VERSION"
mkdir -p "$STAGE"
cp -R plcore portlist.py README.md LICENSE CHANGELOG.md "$STAGE/"
find "$STAGE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
cat > "$STAGE/portlist.cmd" <<'CMD'
@echo off
python "%~dp0portlist.py" %*
CMD
(cd "$OUT" && zip -qr "portlist-$VERSION-windows.zip" "portlist-$VERSION")
ZIP_SHA=$(shasum -a 256 "$OUT/portlist-$VERSION-windows.zip" | cut -d' ' -f1)

# 2. the source tarball, byte-for-byte what GitHub serves for the tag, so the
#    formula's checksum matches what brew downloads.
if git -C "$ROOT" rev-parse "v$VERSION" >/dev/null 2>&1; then
  git -C "$ROOT" archive --format=tar.gz --prefix="portlist-$VERSION/" \
      -o "$OUT/portlist-$VERSION.tar.gz" "v$VERSION"
  TAR_SHA=$(shasum -a 256 "$OUT/portlist-$VERSION.tar.gz" | cut -d' ' -f1)
else
  echo "note: tag v$VERSION does not exist yet, so the formula checksum is left"
  echo "      unstamped. Tag, push, then run this again."
  TAR_SHA=""
fi

# 3. stamp
if [ -n "$TAR_SHA" ]; then
  sed -i.bak -E "s|sha256 \".*\"|sha256 \"$TAR_SHA\"|" packaging/homebrew/portlist.rb
  sed -i.bak -E "s|url \".*\"|url \"https://github.com/Mr-hunt-007/portlist/archive/refs/tags/v$VERSION.tar.gz\"|" packaging/homebrew/portlist.rb
fi
sed -i.bak -E "s|InstallerSha256: .*|InstallerSha256: $ZIP_SHA|" packaging/winget/*.installer.yaml
rm -f packaging/homebrew/*.bak packaging/winget/*.bak

echo
echo "built in dist/:"
ls -1 "$OUT" | sed 's/^/  /'
echo
echo "  windows zip sha256  $ZIP_SHA"
[ -n "$TAR_SHA" ] && echo "  source tar  sha256  $TAR_SHA"
echo
echo "next: gh release create v$VERSION dist/portlist-$VERSION-windows.zip"
