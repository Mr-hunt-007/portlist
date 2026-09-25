# Homebrew formula for portlist. Lives in a tap:
#
#   brew tap Mr-hunt-007/portlist https://github.com/Mr-hunt-007/homebrew-portlist
#   brew install portlist
#
# `sha256` is stamped by scripts/release.sh against the tarball GitHub serves for
# the tag. Do not hand-edit it: a wrong checksum fails the install with a message
# that reads like a compromised download.
class Portlist < Formula
  include Language::Python::Virtualenv

  desc "Every port on this machine, and where it came from"
  homepage "https://mr-hunt-007.github.io/portlist/"
  url "https://github.com/Mr-hunt-007/portlist/archive/refs/tags/v1.4.tar.gz"
  sha256 "41021620ab97d4ccab4eee87e0e0bacaac633c70241c2531c64f098372c4c80c"
  license "MIT"
  head "https://github.com/Mr-hunt-007/portlist.git", branch: "main"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "portlist 1.4", shell_output("#{bin}/portlist --version")
    # --keys prints and exits without touching the terminal, so it is the one
    # part of a curses program that is honest to assert on in a sandbox.
    assert_match "services", shell_output("#{bin}/portlist --keys")
  end
end
