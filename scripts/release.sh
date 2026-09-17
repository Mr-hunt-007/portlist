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
# The zip has to be the same bytes every run. cp -R gives every file the time
# it was copied, so without this the checksum changed on each build and the
# manifest matched only the zip that happened to be uploaded.
#
# The time comes from the tag, not from HEAD: stamping the checksum into the
# manifest is itself a commit, so keying off HEAD means the act of recording a
# hash changes the hash it was recording. Falling back to HEAD before the tag
# exists is fine - the run that matters is the one after the tag is pushed,
# because that is the only run that can stamp the formula.
STAMP_REF="HEAD"
git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null && STAMP_REF="v$VERSION"
find "$STAGE" -exec touch -t "$(git log -1 --format=%cd --date=format:%Y%m%d%H%M "$STAMP_REF")" {} +
(cd "$OUT" && zip -qrX "portlist-$VERSION-windows.zip" "portlist-$VERSION")
ZIP_SHA=$(shasum -a 256 "$OUT/portlist-$VERSION-windows.zip" | cut -d' ' -f1)

# 2. the source tarball, downloaded from GitHub rather than built here.
#    `git archive` does NOT produce the same bytes as GitHub's tarball - it was
#    checked, and the two hashes differed - so stamping a locally built archive
#    gives Homebrew a checksum that will never match, and the install fails with
#    a message that reads like a compromised download. Take the hash from the
#    file brew will actually fetch.
TAR_URL="https://github.com/Mr-hunt-007/portlist/archive/refs/tags/v$VERSION.tar.gz"
if curl -fsSL -o "$OUT/portlist-$VERSION.tar.gz" "$TAR_URL"; then
  TAR_SHA=$(shasum -a 256 "$OUT/portlist-$VERSION.tar.gz" | cut -d' ' -f1)
else
  echo "note: $TAR_URL is not there yet, so the formula checksum is left"
  echo "      unstamped. Tag, push the tag, then run this again."
  TAR_SHA=""
fi

# 3. stamp
#
# Everything that names a version has to move together. A checksum stamped
# beside the PREVIOUS release's URL is the worst of the three states: the
# download succeeds, the hash does not match, and the installer says so in the
# words it reserves for a tampered file.
if [ -n "$TAR_SHA" ]; then
  sed -i.bak -E "s|sha256 \".*\"|sha256 \"$TAR_SHA\"|" packaging/homebrew/portlist.rb
  sed -i.bak -E "s|url \".*\"|url \"https://github.com/Mr-hunt-007/portlist/archive/refs/tags/v$VERSION.tar.gz\"|" packaging/homebrew/portlist.rb
  # The formula's own test asserts the version it prints, so a formula that
  # installs 1.2 and tests for 1.1 fails `brew test` on a working install.
  sed -i.bak -E "s|assert_match \"portlist [0-9.]+\"|assert_match \"portlist $VERSION\"|" packaging/homebrew/portlist.rb
fi
sed -i.bak -E "s|^PackageVersion: .*|PackageVersion: \"$VERSION\"|" packaging/winget/*.yaml
sed -i.bak -E "s|InstallerUrl: .*|InstallerUrl: https://github.com/Mr-hunt-007/portlist/releases/download/v$VERSION/portlist-$VERSION-windows.zip|" packaging/winget/*.installer.yaml
sed -i.bak -E "s|InstallerSha256: .*|InstallerSha256: $ZIP_SHA|" packaging/winget/*.installer.yaml
# The zip's top-level directory is portlist-<version>, so the path winget looks
# for inside it moves too. Stale here, the download succeeds and the install
# fails looking for a directory the archive does not contain.
sed -i.bak -E "s|RelativeFilePath: portlist-[0-9.]+|RelativeFilePath: portlist-$VERSION|" packaging/winget/*.installer.yaml
rm -f packaging/homebrew/*.bak packaging/winget/*.bak

echo
echo "built in dist/:"
ls -1 "$OUT" | sed 's/^/  /'
echo
echo "  windows zip sha256  $ZIP_SHA"
[ -n "$TAR_SHA" ] && echo "  source tar  sha256  $TAR_SHA"
echo
echo "next: gh release create v$VERSION dist/portlist-$VERSION-windows.zip"
