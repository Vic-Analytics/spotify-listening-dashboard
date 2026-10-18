"""
run.py - the collector: fetch recent plays and save the new ones.

Run it with:
    python -m collector.run

This is the script GitHub Actions will run every hour (Phase 4).
It is safe to run as often as you like: plays already in the database are
skipped, so running it twice in a row adds nothing the second time.
"""

from collector.fetch import fetch_recent_plays
from collector.spotify_client import get_spotify_client
from database.db import count_plays, get_connection, get_db_path, save_plays


def main() -> None:
    sp = get_spotify_client()
    plays = fetch_recent_plays(sp)

    conn = get_connection()
    added, skipped = save_plays(conn, plays, source="api")

    print(f"Fetched {len(plays)} plays from Spotify")
    print(f"  {added} new, saved")
    print(f"  {skipped} already in the database, skipped")
    print(f"Database now holds {count_plays(conn)} plays ({get_db_path()})")
    conn.close()


if __name__ == "__main__":
    main()
