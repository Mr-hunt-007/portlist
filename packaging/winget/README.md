# winget manifests

Three files, the shape winget expects:

    manifests/m/Mr-hunt-007/portlist/1.1/
      Mr-hunt-007.portlist.yaml               version manifest
      Mr-hunt-007.portlist.installer.yaml     installer manifest
      Mr-hunt-007.portlist.locale.en-US.yaml  locale manifest

`InstallerSha256` is stamped by `scripts/release.sh` from the release zip.

**What Windows needs that macOS and Linux do not.** CPython on Windows ships
without `curses`, and portlist is a curses program. The zip below is the source
plus a `portlist.cmd` shim, so it needs Python 3.9+ on PATH and the
`windows-curses` wheel. `pipx install portlist` handles both on its own and is
the route worth recommending; the manifest declares the Python dependency and
the description says the rest out loud rather than failing at the first keypress.

Submit with:

    winget validate --manifest manifests/m/Mr-hunt-007/portlist/1.1
    winget install --manifest manifests/m/Mr-hunt-007/portlist/1.1
