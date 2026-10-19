"""
publish_public.py - copy this project's code to the PUBLIC portfolio repo,
with a privacy-safe commit identity.

    python -m scripts.publish_public --dry-run     # check everything, push nothing
    python -m scripts.publish_public               # check, then push

Why it exists: the code lives in a private repo (which also holds the real
listening data on a separate "data" branch). Commits there carry a personal
email address. A public repo must not show it, and must never receive the data
branch. So this script:

  1. clones ONLY the main branch into a temporary folder (your real repo is
     never modified),
  2. rewrites every commit's author and committer to the GitHub "noreply"
     identity,
  3. scans the rewritten history for your personal email, your Spotify
     credentials, and any database or raw-data files, and refuses to continue
     if it finds any,
  4. pushes to the public repo. It never force-pushes. The rewrite gives the
     same commit IDs every time, so each publish is a normal fast-forward.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values

from database.db import PROJECT_ROOT

PUBLIC_REPO_URL = "https://github.com/Vic-Analytics/spotify-listening-dashboard.git"
PUBLIC_NAME = "Vic-Analytics"
PUBLIC_EMAIL = "341802042+Vic-Analytics@users.noreply.github.com"   # GitHub's privacy address


def git(*args, cwd, check=True) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace",
                            env={**os.environ, "FILTER_BRANCH_SQUELCH_WARNING": "1"})
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout


def forbidden_strings() -> dict:
    """Things that must never appear in the public history. Read at run time, so
    they are never written into this (public) file."""
    needles = {}
    email = git("config", "user.email", cwd=PROJECT_ROOT, check=False).strip()
    if email:
        needles["your personal git email"] = email
    secrets = dotenv_values(PROJECT_ROOT / ".env")
    for key in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN"):
        if secrets.get(key):
            needles[key] = secrets[key].strip().strip("'\"")
    return needles


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    if git("status", "--porcelain", cwd=PROJECT_ROOT).strip():
        raise SystemExit("You have uncommitted changes. Commit them first, so the public copy is complete.")
    if git("rev-parse", "--abbrev-ref", "HEAD", cwd=PROJECT_ROOT).strip() != "main":
        raise SystemExit("Switch to the main branch first.")

    needles = forbidden_strings()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        copy = Path(folder) / "public_copy"

        print("1. Cloning main only (the data branch is never included) ...")
        git("clone", "-q", "--single-branch", "--branch", "main", "--no-hardlinks",
            str(PROJECT_ROOT), str(copy), cwd=folder)

        print("2. Rewriting commit identities ...")
        env_filter = (f"export GIT_AUTHOR_NAME='{PUBLIC_NAME}' GIT_AUTHOR_EMAIL='{PUBLIC_EMAIL}' "
                      f"GIT_COMMITTER_NAME='{PUBLIC_NAME}' GIT_COMMITTER_EMAIL='{PUBLIC_EMAIL}'")
        git("filter-branch", "-f", "--env-filter", env_filter, "--", "main", cwd=copy)
        # Remove the clone's pointer back to the original history and filter-branch's backup.
        for ref in git("for-each-ref", "--format=%(refname)", "refs/original", cwd=copy).split():
            git("update-ref", "-d", ref, cwd=copy)
        git("remote", "remove", "origin", cwd=copy)
        git("reflog", "expire", "--expire=now", "--all", cwd=copy)
        git("gc", "-q", "--prune=now", cwd=copy)

        print("3. Scanning the public history for private data ...")
        history = git("log", "--all", "-p", "--format=%an %ae %cn %ce%n%B", cwd=copy)
        problems = [f"{label} appears in the history" for label, text in needles.items() if text in history]
        for path in set(git("log", "--all", "--name-only", "--format=", cwd=copy).split()):
            is_sample = path == "data/sample/sample.db"
            if (path.endswith((".db", ".sqlite", ".sqlite3")) and not is_sample) or path == ".env" \
                    or (path.startswith("data/raw/") and not path.endswith(".gitkeep")):
                problems.append(f"private file in history: {path}")
        if problems:
            raise SystemExit("STOPPED. Not publishing:\n  - " + "\n  - ".join(problems))
        print(f"   OK ({len(needles)} secrets/identifiers checked, no private files found)")

        print("4. Comparing with the public repo ...")
        git("remote", "add", "origin", PUBLIC_REPO_URL, cwd=copy)
        fetched = subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=copy, capture_output=True, text=True)
        if fetched.returncode == 0:
            if subprocess.run(["git", "merge-base", "--is-ancestor", "FETCH_HEAD", "HEAD"], cwd=copy).returncode != 0:
                raise SystemExit("The public repo has commits that this copy lacks (history diverged). "
                                 "Not pushing, and never force-pushing.")
            new = git("log", "--format=  %h %s", "FETCH_HEAD..HEAD", cwd=copy).rstrip()
        else:
            new = git("log", "--format=  %h %s", cwd=copy).rstrip()   # first publish
        if not new:
            print("   The public repo is already up to date.")
            return
        print("   Commits to publish:\n" + new)

        if dry_run:
            print("\nDry run: nothing was pushed.")
            return
        print("5. Pushing ...")
        git("push", "origin", "main", cwd=copy)
        print("Done: " + PUBLIC_REPO_URL.removesuffix(".git"))


if __name__ == "__main__":
    main()
