# winget manifests

These are correct, and they cannot be submitted. Keep them for the record, not
for use.

## Why

A portable winget package may point at exactly one kind of file:

```cpp
// microsoft/winget-cli, src/AppInstallerCommonCore/Manifest/ManifestValidation.cpp
constexpr std::array<std::wstring_view, 1> s_AllowedPortableFiletypes = {
    L".exe",
};
```

What ships for Windows is the source plus a `portlist.cmd` shim, because CPython
on Windows has no `curses` and portlist is a curses program: the package needs
Python on PATH and the `windows-curses` wheel either way. A `.cmd` file is not
an `.exe`, so `microsoft/winget-pkgs` rejects the manifest during validation:

    [Error] InvalidPortableFiletype: The file type of the referenced file is
    not allowed. (RelativeFilePath)

That is a rule about file extensions, not about this manifest, so no edit to
these three files fixes it. Submitted as microsoft/winget-pkgs#436665 and closed
for this reason.

## What would fix it, and why it was not done

Shipping a compiled `portlist.exe` launcher in the zip. It would still need
Python on PATH, so it buys the winget listing and nothing else, at the cost of a
cross-compiler in the release path and an unsigned binary in a project that
otherwise ships nothing but Python.

`pipx install portlist-tui` handles Windows properly today: it declares
`windows-curses` as a dependency there and installs it into the same isolated
environment. That is the route the docs recommend.

## The shape, if this is ever revisited

    manifests/m/Mr-hunt-007/portlist/1.2/
      Mr-hunt-007.portlist.yaml               version manifest
      Mr-hunt-007.portlist.installer.yaml     installer manifest
      Mr-hunt-007.portlist.locale.en-US.yaml  locale manifest

They are at manifest spec 1.12.0, and `scripts/release.sh` stamps
`PackageVersion`, `InstallerUrl`, `InstallerSha256` (upper case, as that
repository writes it) and the version inside `RelativeFilePath`. Validate with
`winget validate --manifest <dir>` on Windows; schema validation alone passes
and is not sufficient, which is how the `.exe` rule was found.
