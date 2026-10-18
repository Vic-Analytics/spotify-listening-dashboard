"""
fetch.py - Phase 2: ask Spotify for your last 50 plays and flatten them.

Run it with:
    python -m collector.fetch           # prints a readable table
    python -m collector.fetch --raw     # also prints one untouched API item

Spotify answers with deeply nested JSON (a play contains a track, which
contains an album and a list of artists...). A database table is flat, like a
spreadsheet: one row per play, one column per fact. The job of this file is
that conversion. Phase 3 will take these flat rows and store them in SQLite.

Things worth knowing about this endpoint:
  * It returns at most 50 plays, newest first. Older plays are gone for good,
    which is why we poll every hour and save them ourselves.
  * `played_at` is the moment the track FINISHED (or was stopped), in UTC.
  * A track only appears if you listened for 30+ seconds.
  * It does NOT say how long you listened or whether you skipped. Only the
    Extended Streaming History export has that (Phase 5).
"""

import json
import sys

from collector.spotify_client import get_spotify_client


def flatten_play(item: dict) -> dict:
    """Turn one nested API item into one flat row (a plain dict)."""
    track = item["track"]
    artists = track.get("artists", [])

    # A track can have several artists. We keep the first as the "main" artist
    # (used for Top Artists) and also keep everyone, joined into one string.
    main_artist = artists[0] if artists else {}

    # `context` says where you played from (a playlist, an album...).
    # It is None for plays that came from search results, for example.
    context = item.get("context") or {}

    return {
        "played_at": item["played_at"],          # e.g. "2026-10-17T12:34:56.789Z"
        "track_uri": track.get("uri"),           # "spotify:track:..." always present, even for local files
        "track_id": track.get("id"),             # None for local files
        "track_name": track.get("name"),
        "artist_id": main_artist.get("id"),
        "artist_name": main_artist.get("name"),
        "all_artists": ", ".join(a.get("name", "") for a in artists),
        "album_name": track.get("album", {}).get("name"),
        "duration_ms": track.get("duration_ms"), # full length of the track, not time listened
        "context_type": context.get("type"),     # "playlist", "album", "artist" or None
    }


def fetch_recent_plays(sp) -> list[dict]:
    """Fetch the last 50 plays and return them as a list of flat rows."""
    response = sp.current_user_recently_played(limit=50)
    return [flatten_play(item) for item in response["items"]]


def main() -> None:
    sp = get_spotify_client()

    if "--raw" in sys.argv:
        # Show the ORIGINAL nested JSON for one play, so you can see exactly
        # what the flattening above is doing.
        raw = sp.current_user_recently_played(limit=1)
        print(json.dumps(raw["items"][0], indent=2)[:3000])
        print("\n--- (cut off at 3000 characters) ---\n")

    plays = fetch_recent_plays(sp)
    print(f"Fetched {len(plays)} plays.\n")

    # Print a simple aligned table. [:19] trims "2026-10-17T12:34:56" off the timestamp.
    print(f"{'played_at (UTC)':<20} {'artist':<22} {'track':<34} {'from':<9}")
    print("-" * 88)
    for p in plays:
        print(
            f"{p['played_at'][:19]:<20} "
            f"{(p['artist_name'] or '?')[:21]:<22} "
            f"{(p['track_name'] or '?')[:33]:<34} "
            f"{p['context_type'] or '-':<9}"
        )


if __name__ == "__main__":
    main()
