# Setup

portlist is one Python program with no dependencies on macOS, Linux or BSD. Pick
whichever route below matches how you like to install things; they all end with
`portlist` on your PATH.

## Homebrew (macOS, Linux)

```sh
brew tap Mr-hunt-007/portlist https://github.com/Mr-hunt-007/homebrew-portlist
brew trust mr-hunt-007/portlist      # Homebrew asks this of every third-party tap
brew install portlist
```

The `brew trust` line is not optional: Homebrew refuses to load a formula from a
tap it has not been told to trust, and says so rather than installing anything.

Puts the program in Homebrew's prefix with its own Python. `brew upgrade portlist`
updates it, `brew uninstall portlist` removes it, and nothing is left behind
except `~/.portlist`, which is yours to delete.

## winget (Windows)

**Not submitted yet.** The manifests are written and validated in
`packaging/winget/`, but nothing has been sent to `microsoft/winget-pkgs`, so
`winget install Mr-hunt-007.portlist` will not find anything today. Use pipx
below, which is the better route on Windows anyway.

Windows needs one thing macOS and Linux do not: CPython ships there without
`curses`, and portlist is a curses program. The winget package installs the
source and a shim, so you also need `pip install windows-curses`. If that is a
sentence you would rather not think about, use pipx below, which handles it.

## pipx (anywhere)

```sh
pipx install git+https://github.com/Mr-hunt-007/portlist
pip  install git+https://github.com/Mr-hunt-007/portlist
```

The simplest route on Windows, because `windows-curses` is declared as a
dependency there and pipx installs it into the same isolated environment.

Installing straight from the repository rather than from PyPI, because nothing
has been uploaded there yet. When it is, the distribution will be
**`portlist-tui`**: the name `portlist` on PyPI belongs to an unrelated package,
and shipping under it would mean `pip install portlist` quietly fetching
somebody else's code. The command it installs is `portlist` either way.

Remove with `pipx uninstall portlist-tui`.

## One line

```sh
curl -fsSL https://mr-hunt-007.github.io/portlist/install.sh | sh
```

Installs to `~/.local/lib/portlist` with a shim at `~/.local/bin/portlist`. No
root, nothing system-wide, no package manager involved. Set `PORTLIST_PREFIX` to
put it somewhere else.

Piping a script into a shell is a thing worth being suspicious of, so
[read it first](https://mr-hunt-007.github.io/portlist/install.sh): it is short,
it fetches one tarball, and it writes to two directories.

To remove: `rm -rf ~/.local/lib/portlist ~/.local/bin/portlist`.

## From source

```sh
git clone https://github.com/Mr-hunt-007/portlist
cd portlist
python3 portlist.py
```

No build step. `python3 -m plcore` works too, and `pip install .` gives you the
`portlist` command.

## Requirements

- Python 3.9 or newer, with `curses` (standard everywhere except Windows).
- macOS, Linux, BSD or Windows.
- No third-party packages, except `windows-curses` on Windows.

## Where it keeps things

`~/.portlist/` holds the launch ledger, the use history and the recipe book.
Override with `--data-dir` or the `PORTLIST_DATA` environment variable. Delete
the directory and portlist starts over knowing nothing; the only thing lost is
history it observed itself.

## Checking an install

```sh
portlist --version
portlist --keys
```

Both print and exit without touching the terminal, which makes them safe in a
script or a container.
