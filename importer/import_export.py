"""
import_export.py - Phase 5: load your Extended Streaming History into the database.

Run it with:
    python -m importer.import_export                 # reads everything under data/raw
    python -m importer.import_export "path\\to\\folder"

It does three jobs:
  1. READ   every Streaming_History_Audio_*.json file in the folder.
  2. CLEAN  each record: drop podcasts/audiobooks/bad rows, tidy the text,
            convert timestamps and true/false values into our database format.
            The IP address in the export is deliberately never copied.
  3. MERGE  into the same `plays` table the API collector uses, without
            creating duplicates (details in merge_into_db below).

Safe to run repeatedly: the second run adds nothing new.
"""

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from database.db import PROJECT_ROOT, count_plays, get_connection, get_db_path, normalize_timestamp

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"

# The export labels devices with long, messy strings such as
# "ios 17.0 (iPhone14,5)" and "Windows 10 (10.0.19044; x64)", with inconsistent
# capitalisation ("ios" vs "iOS"). We keep just the device FAMILY, spelled
# consistently, so we can later ask "how much do I listen on my phone vs PC?".
_PLATFORM_FAMILIES = {
    "ios": "iOS",
    "windows": "Windows",
    "android": "Android",
    "xbox": "Xbox",
    "osx": "macOS",
    "os": "macOS",
    "mac": "macOS",
    "linux": "Linux",
    "web_player": "Web",
}


def normalize_platform(raw) -> str:
    """'Windows 10 (10.0.19044; x64)' -> 'Windows',  'ios 17.0 (...)' -> 'iOS'."""
    if not raw or not str(raw).strip():
        return "Unknown"
    first_word = str(raw).strip().split()[0]
    return _PLATFORM_FAMILIES.get(first_word.lower(), first_word)


def _blank_to_none(value):
    """Turn '' or whitespace-only text into None (SQL NULL = 'no value')."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def clean_record(rec: dict):
    """
    Clean ONE export record.
    Returns (row, None) if it is a usable music play, or (None, reason) if it
    should be dropped. The reason is counted in the final report.
    """
    track_uri = _blank_to_none(rec.get("spotify_track_uri"))

    # --- Drop things that are not music tracks ---
    if track_uri is None:
        if rec.get("spotify_episode_uri"):
            return None, "podcast episode"
        if rec.get("audiobook_uri") or rec.get("audiobook_chapter_uri"):
            return None, "audiobook"
        return None, "no track URI"

    # --- Drop records with unusable numbers/dates ---
    ms_played = rec.get("ms_played")
    if not isinstance(ms_played, int) or ms_played < 0:
        return None, "invalid ms_played"
    try:
        played_at = normalize_timestamp(rec["ts"])
    except (KeyError, ValueError, TypeError):
        return None, "invalid timestamp"

    # 'spotify:track:abc123' -> 'abc123'
    track_id = track_uri.split(":")[-1] if track_uri.startswith("spotify:track:") else None

    row = {
        "played_at": played_at,
        "track_uri": track_uri,
        "track_id": track_id,
        "track_name": _blank_to_none(rec.get("master_metadata_track_name")),
        "artist_name": _blank_to_none(rec.get("master_metadata_album_artist_name")),
        "album_name": _blank_to_none(rec.get("master_metadata_album_album_name")),
        "ms_played": ms_played,
        # JSON true/false -> SQLite 1/0 (None stays None = "unknown")
        "skipped": None if rec.get("skipped") is None else int(bool(rec["skipped"])),
        "reason_start": _blank_to_none(rec.get("reason_start")),
        "reason_end": _blank_to_none(rec.get("reason_end")),
        "shuffle": None if rec.get("shuffle") is None else int(bool(rec["shuffle"])),
        "platform": normalize_platform(rec.get("platform")),
        # Columns that only the API provides:
        "artist_id": None,
        "all_artists": None,
        "duration_ms": None,
        "context_type": None,
    }
    # NOTE: rec["ip_addr"] and rec["conn_country"] are intentionally ignored.
    # They are personal data and no chart needs them.
    return row, None


def find_export_files(raw_dir: Path) -> list[Path]:
    """All audio history files under raw_dir, in a stable order."""
    return sorted(Path(raw_dir).rglob("Streaming_History_Audio_*.json"))


def read_export(files: list[Path]):
    """
    Read and clean every file. Returns (rows, stats).
    Files are processed one at a time, and each raw record is cleaned and then
    discarded, so memory stays small even with ~300,000 records.
    """
    stats = Counter()
    rows = []
    seen = set()  # (played_at, track_uri) pairs already collected

    for path in files:
        records = json.loads(path.read_text(encoding="utf-8"))
        stats["records read"] += len(records)

        for rec in records:
            row, drop_reason = clean_record(rec)
            if row is None:
                stats[f"dropped: {drop_reason}"] += 1
                continue

            # Neighbouring export files overlap slightly, so the same play can
            # appear twice. Keep only the first copy.
            key = (row["played_at"], row["track_uri"])
            if key in seen:
                stats["dropped: duplicate within export"] += 1
                continue
            seen.add(key)
            rows.append(row)

    stats["usable plays"] = len(rows)
    return rows, stats


# Columns copied from the staging table. (`id` is left out: SQLite numbers new rows itself.)
_STAGING_COLUMNS = (
    "played_at, track_uri, track_id, track_name, artist_name, artist_id, "
    "all_artists, album_name, duration_ms, ms_played, skipped, context_type, "
    "reason_start, reason_end, shuffle, platform, source, collected_at"
)


def merge_into_db(conn, rows: list[dict]) -> dict:
    """
    Merge cleaned export rows into `plays`. Returns counts for the report.

    The API collector and the export describe the SAME plays for any period
    they overlap. They agree on the end time to the second (we verified this on
    your data), so (played_at, track_uri) identifies a play in both. For each
    export row there are two cases:

      * The play is already in the database from the API:
          don't add a second copy. The export knows things the API doesn't
          (ms_played, skipped, how it started/ended), so we COPY those onto
          the existing API row. -> "enriched"
      * It is not there yet: insert it as a new row. -> "added"

    We do this in SQL with a temporary "staging" table, so the database does
    the matching instead of a slow Python loop.
    """
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Stage: a scratch table with the same columns as `plays`, no rules attached.
    conn.execute("DROP TABLE IF EXISTS temp.staging")
    conn.execute("CREATE TEMP TABLE staging AS SELECT * FROM plays WHERE 0")
    for row in rows:
        row["source"] = "export"
        row["collected_at"] = collected_at
    conn.executemany(
        """INSERT INTO temp.staging (
               played_at, track_uri, track_id, track_name, artist_name, artist_id,
               all_artists, album_name, duration_ms, ms_played, skipped, context_type,
               reason_start, reason_end, shuffle, platform, source, collected_at
           ) VALUES (
               :played_at, :track_uri, :track_id, :track_name, :artist_name, :artist_id,
               :all_artists, :album_name, :duration_ms, :ms_played, :skipped, :context_type,
               :reason_start, :reason_end, :shuffle, :platform, :source, :collected_at
           )""",
        rows,
    )

    # 2. Enrich: copy export-only facts onto API rows that match.
    #    `ms_played IS NULL` means "not enriched yet", which keeps re-runs harmless.
    enriched = conn.execute(
        """
        UPDATE plays
           SET ms_played    = s.ms_played,
               skipped      = s.skipped,
               reason_start = s.reason_start,
               reason_end   = s.reason_end,
               shuffle      = s.shuffle,
               platform     = s.platform
          FROM temp.staging AS s
         WHERE plays.played_at = s.played_at
           AND plays.track_uri = s.track_uri
           AND plays.source    = 'api'
           AND plays.ms_played IS NULL
        """
    ).rowcount

    # 3. Add: everything else. INSERT OR IGNORE skips rows that already exist
    #    (the UNIQUE rule), including the ones we just enriched above.
    added = conn.execute(
        f"INSERT OR IGNORE INTO plays ({_STAGING_COLUMNS}) "
        f"SELECT {_STAGING_COLUMNS} FROM temp.staging"
    ).rowcount

    conn.commit()
    conn.execute("DROP TABLE temp.staging")
    return {
        "added": added,
        "enriched": enriched,
        "already present": len(rows) - added - enriched,
    }


def main() -> None:
    raw_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RAW_DIR
    files = find_export_files(raw_dir)
    if not files:
        raise SystemExit(
            f"No Streaming_History_Audio_*.json files found under {raw_dir}.\n"
            "Extract your Spotify export into data/raw first."
        )

    print(f"Reading {len(files)} files from {raw_dir} ...")
    rows, stats = read_export(files)

    conn = get_connection()
    before = count_plays(conn)
    result = merge_into_db(conn, rows)
    after = count_plays(conn)

    print("\n--- Cleaning report ---")
    for label in sorted(stats, key=lambda k: (k.startswith("dropped"), k)):
        print(f"  {label:<36} {stats[label]:>9,}")

    print("\n--- Merge report ---")
    print(f"  {'new rows added':<36} {result['added']:>9,}")
    print(f"  {'API rows enriched with export data':<36} {result['enriched']:>9,}")
    print(f"  {'already in database (re-run)':<36} {result['already present']:>9,}")
    print(f"\nDatabase: {before:,} -> {after:,} plays  ({get_db_path()})")
    conn.close()


if __name__ == "__main__":
    main()
