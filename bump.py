#!/usr/bin/env python3
"""
Bump the project version in one shot: VERSION, app.py, and CHANGELOG.md.

Usage:
    ./bump.py patch          # 0.1.0 -> 0.1.1
    ./bump.py minor          # 0.1.0 -> 0.2.0
    ./bump.py major          # 0.1.0 -> 1.0.0
    ./bump.py 1.4.2          # set explicitly
    ./bump.py minor --commit # also git add, commit, and tag vX.Y.Z

What it does:
    - reads the current version from VERSION
    - writes the new version to VERSION and app.py (__version__)
    - in CHANGELOG.md: renames the [Unreleased] section to the new version
      with today's date, leaves a fresh empty [Unreleased] above it, and
      refreshes the compare/release links at the bottom.
"""

import datetime as dt
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(HERE, "VERSION")
APP_FILE = os.path.join(HERE, "app.py")
CHANGELOG = os.path.join(HERE, "CHANGELOG.md")
REPO = "https://github.com/shossain786/video-editor"


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read_current() -> tuple[int, int, int]:
    with open(VERSION_FILE) as f:
        raw = f.read().strip()
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", raw)
    if not m:
        die(f"VERSION does not hold a valid semver: {raw!r}")
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def next_version(cur: tuple[int, int, int], arg: str) -> str:
    major, minor, patch = cur
    if arg == "major":
        return f"{major + 1}.0.0"
    if arg == "minor":
        return f"{major}.{minor + 1}.0"
    if arg == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if re.fullmatch(r"\d+\.\d+\.\d+", arg):
        return arg
    die(f"unknown bump: {arg!r} (use major|minor|patch or an explicit X.Y.Z)")


def update_version_file(new: str) -> None:
    with open(VERSION_FILE, "w") as f:
        f.write(new + "\n")


def update_app(new: str) -> None:
    with open(APP_FILE) as f:
        src = f.read()
    updated, n = re.subn(
        r'__version__\s*=\s*"[^"]*"', f'__version__ = "{new}"', src, count=1)
    if n != 1:
        die("could not find __version__ in app.py")
    with open(APP_FILE, "w") as f:
        f.write(updated)


def update_changelog(new: str, prev: str) -> None:
    with open(CHANGELOG) as f:
        text = f.read()

    today = dt.date.today().isoformat()
    if "## [Unreleased]" not in text:
        die("CHANGELOG.md has no '## [Unreleased]' section to promote")

    # Rename [Unreleased] -> new version, and prepend a fresh empty Unreleased.
    text = text.replace(
        "## [Unreleased]",
        f"## [Unreleased]\n\n## [{new}] - {today}",
        1,
    )

    # Refresh link references at the bottom.
    text = re.sub(
        r"\[Unreleased\]:.*",
        f"[Unreleased]: {REPO}/compare/v{new}...HEAD",
        text, count=1)
    # Insert the new release link right after the Unreleased link line.
    new_link = f"[{new}]: {REPO}/compare/v{prev}...v{new}"
    text = re.sub(
        r"(\[Unreleased\]:.*\n)",
        rf"\1{new_link}\n",
        text, count=1)

    with open(CHANGELOG, "w") as f:
        f.write(text)


def git(*args: str) -> None:
    subprocess.run(["git", "-C", HERE, *args], check=True)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    bump = sys.argv[1]
    do_commit = "--commit" in sys.argv[2:]

    cur = read_current()
    prev = ".".join(map(str, cur))
    new = next_version(cur, bump)
    if new == prev:
        die(f"new version equals current ({new})")

    update_version_file(new)
    update_app(new)
    update_changelog(new, prev)
    print(f"bumped {prev} -> {new}")
    print("  updated: VERSION, app.py, CHANGELOG.md")

    if do_commit:
        git("add", "VERSION", "app.py", "CHANGELOG.md")
        git("commit", "-m", f"Release v{new}")
        git("tag", "-a", f"v{new}", "-m", f"v{new}")
        print(f"  committed and tagged v{new}")
        print(f"  push with: git push && git push origin v{new}")
    else:
        print("  review the changes, then commit and tag when ready")


if __name__ == "__main__":
    main()
