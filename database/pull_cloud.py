"""
pull_cloud.py - copy plays collected by GitHub Actions into your LOCAL database.

Run it with:
    python -m database.pull_cloud                    # download from GitHub, then merge
    python -m database.pull_cloud --file some.db     # merge from a database file you already have

Why this exists: two databases are growing in parallel.
  * CLOUD  (data branch on GitHub): only what the hourly collector saw. Small.
  * LOCAL  (data/spotify.db):       your full history, including the export.
Run this whenever you want your local copy (and so the dashboard) to catch up.

Safe by design:
  * It only ADDS plays that your local database does not have yet.
  * It never changes or deletes an existing local row, so the extra detail the
    export gave you (ms_played, skips, ...) cannot be overwritten.
  * Running it twice in a row adds nothing the second time.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from database.db import PROJECT_ROOT, count_plays, get_connection, get_db_path

# A healthy cloud database is API-only and small. If it is much bigger, the
# full local database was probably pushed there by mistake (GitHub rejects
# files over 100 MB), so we warn.
CLOUD_SIZE_WARNING_BYTES = 30 * 1024 * 1024


def download_cloud_db(destination: Path) -> None:
    """Fetch the `data` branch (read-only) and save its spotify.db to `destination`."""
    fetch = subprocess.run(
        ["git", "fetch", "origin", "data"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    if fetch.returncode != 0:
        raise RuntimeError(
            "Could not fetch the 'data' branch from GitHub.\n"
            "Has the hourly workflow run at least once, and are you signed in to git?\n"
            f"git said: {fetch.stderr.strip()}"
        )

    # `git show branch:file` prints the file's bytes. We capture them as bytes
    # (no text=True) because a database is binary, not text.
    show = subprocess.run(
        ["git", "show", "origin/data:spotify.db"],
        cwd=PROJECT_ROOT, capture_output=True,
    )
    if show.returncode != 0 or not show.stdout:
        raise RuntimeError("The data branch has no spotify.db yet.")
    destination.write_bytes(show.stdout)


def merge_from_file(conn, cloud_db_path: Path) -> dict:
    """
    Add every play from the cloud database file that `conn` does not already have.
    Returns {"in cloud": n, "added": n, "already local": n}.
    """
    # ATTACH lets one connection see a second database file, named `cloud`.
    # Then plain SQL can copy rows between the two databases.
    conn.commit()  # ATTACH cannot happen in the middle of a transaction
    conn.execute("ATTACH DATABASE ? AS cloud", (str(cloud_db_path),))
    try:
        local_cols = [r["name"] for r in conn.execute("PRAGMA main.table_info(plays)")]
        cloud_cols = {r["name"] for r in conn.execute("PRAGMA cloud.table_info(plays)")}
        if not cloud_cols:
            raise RuntimeError("That database has no `plays` table.")

        # Copy only columns that exist on BOTH sides. This keeps the script
        # working if the cloud database is from an older version of the schema.
        # (`id` is skipped: each database numbers its own rows.)
        columns = [c for c in local_cols if c in cloud_cols and c != "id"]
        column_list = ", ".join(columns)

        in_cloud = conn.execute("SELECT COUNT(*) FROM cloud.plays").fetchone()[0]
        added = conn.execute(
            f"INSERT OR IGNORE INTO main.plays ({column_list}) "
            f"SELECT {column_list} FROM cloud.plays ORDER BY played_at"
        ).rowcount
        conn.commit()
    finally:
        conn.execute("DETACH DATABASE cloud")

    return {"in cloud": in_cloud, "added": added, "already local": in_cloud - added}


def main() -> None:
    conn = get_connection()
    before = count_plays(conn)
    latest_before = conn.execute("SELECT MAX(played_at) FROM plays").fetchone()[0]

    if "--file" in sys.argv:
        cloud_path = Path(sys.argv[sys.argv.index("--file") + 1])
        result = merge_from_file(conn, cloud_path)
    else:
        with tempfile.TemporaryDirectory() as folder:
            cloud_path = Path(folder) / "cloud_spotify.db"
            print("Downloading the database from the GitHub data branch ...")
            download_cloud_db(cloud_path)
            size = cloud_path.stat().st_size
            if size > CLOUD_SIZE_WARNING_BYTES:
                print(f"WARNING: the cloud database is {size / 1e6:.0f} MB. It should be tiny "
                      "(API plays only). Was your full local database pushed to the data branch?")
            result = merge_from_file(conn, cloud_path)

    after = count_plays(conn)
    latest_after = conn.execute("SELECT MAX(played_at) FROM plays").fetchone()[0]

    print(f"\nPlays in the cloud database : {result['in cloud']:,}")
    print(f"New plays added locally     : {result['added']:,}")
    print(f"Already in local database   : {result['already local']:,}")
    print(f"\nLocal database: {before:,} -> {after:,} plays  ({get_db_path()})")
    print(f"Most recent play: {latest_before} -> {latest_after}")
    conn.close()


if __name__ == "__main__":
    main()
