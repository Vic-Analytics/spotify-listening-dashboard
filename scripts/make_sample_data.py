"""
make_sample_data.py - generate a FAKE listening history for the public demo.

Run it with:
    python -m scripts.make_sample_data

It writes data/sample/sample.db using exactly the same table layout as your
real database, so the dashboard code is identical for both. Nothing in it comes
from your Spotify account: artists and tracks are invented, and the random
generator uses a fixed seed, so every run produces the same file.

The fake listener is designed to show off every chart:
  * active streaks separated by quiet gaps        -> streaks chart
  * new artists appearing gradually               -> discovery chart
  * weekday commute + evening habits, late weekends -> heatmap
  * skip rate that creeps upward over time        -> skip charts
  * skipping that grows as a session goes on      -> skip-fatigue chart (an invented pattern)
  * 1-3 sessions a day, separated by long pauses  -> sessions tab
Times are generated as UTC and the dashboard shows the sample in UTC.
"""

import math
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from database.db import PROJECT_ROOT, get_connection, save_plays

SAMPLE_DB = PROJECT_ROOT / "data" / "sample" / "sample.db"

SEED = 42
START = date(2025, 1, 1)
END = date(2026, 6, 30)
ARTIST_COUNT = 70

# Invented names are built from made-up syllables so they don't point at real artists.
SYLLABLES = ["lu", "mo", "ra", "vel", "ki", "zan", "to", "mir", "elle", "dax", "ven", "sol",
             "ari", "no", "bex", "quil", "fen", "ora", "tay", "wyn", "jor", "ume", "lix", "pax"]
SUFFIXES = ["", "", " Club", " & The Static", " Parade", " Quartet", " Radio", " Collective"]

# Probability of starting a listening session at each hour (UTC), by day type.
WEEKDAY_HOURS = {7: 3, 8: 6, 9: 3, 12: 4, 13: 4, 17: 3, 18: 4, 19: 5, 20: 6, 21: 6, 22: 4, 23: 2}
WEEKEND_HOURS = {10: 2, 11: 4, 12: 5, 13: 5, 14: 4, 16: 3, 18: 4, 20: 6, 21: 6, 22: 5, 23: 3, 0: 2}


def make_artists(rng: random.Random) -> list[dict]:
    """Invent artists. Early artists are known from day 1; the rest get
    'discovered' gradually over the period."""
    names = set()
    while len(names) < ARTIST_COUNT:
        name = "".join(rng.choice(SYLLABLES) for _ in range(rng.randint(2, 3))).capitalize()
        names.add(name + rng.choice(SUFFIXES))
    names = sorted(names)
    rng.shuffle(names)

    total_days = (END - START).days
    artists = []
    for rank, name in enumerate(names):
        known_from = 0 if rank < 14 else int(rng.uniform(0, total_days - 20))
        tracks = [
            {"title": f"{rng.choice(['Midnight', 'Paper', 'Glass', 'Slow', 'Neon', 'Quiet', 'Golden', 'Static'])} "
                      f"{rng.choice(['Harbor', 'Signals', 'Weather', 'Orchard', 'Echoes', 'Letters', 'Summer', 'Engine'])}",
             "seconds": rng.randint(130, 270)}
            for _ in range(rng.randint(4, 11))
        ]
        artists.append({
            "name": name,
            "weight": 1 / (rank + 1) ** 0.7,   # a few favourites, a long tail
            "known_from": known_from,
            "tracks": tracks,
            "id": rank,
        })
    return artists


def pick_artist(rng, artists, day_number):
    available = [a for a in artists if a["known_from"] <= day_number]
    # New discoveries get extra attention for their first three weeks.
    weights = [a["weight"] * (3 if day_number - a["known_from"] < 21 else 1) for a in available]
    return rng.choices(available, weights)[0]


def generate_plays(rng, artists) -> list[dict]:
    plays = []
    total_days = (END - START).days + 1
    active = True

    for day_number in range(total_days):
        today = START + timedelta(days=day_number)

        # Streaks: usually keep listening day after day, occasionally take a break.
        active = rng.random() < (0.94 if active else 0.35)
        if not active:
            continue

        plays_today = max(4, min(90, int(rng.lognormvariate(2.8, 0.55))))
        profile = WEEKEND_HOURS if today.weekday() >= 5 else WEEKDAY_HOURS
        session_count = rng.randint(1, 3)
        skip_base = 0.20 + 0.40 * day_number / total_days   # skipping creeps up over time

        for _ in range(session_count):
            hour = rng.choices(list(profile), list(profile.values()))[0]
            clock = datetime(today.year, today.month, today.day, hour,
                             rng.randint(0, 59), tzinfo=timezone.utc)
            shuffle = rng.random() < 0.6
            platform = rng.choices(["iOS", "Windows", "Android"], [0.65, 0.25, 0.10])[0]
            skip_prob = min(0.9, skip_base * (1.35 if shuffle else 0.5))

            reason_start = "clickrow"
            for position in range(max(1, plays_today // session_count)):
                artist = pick_artist(rng, artists, day_number)
                track = rng.choices(artist["tracks"], [1 / (i + 1) ** 0.5 for i in range(len(artist["tracks"]))])[0]
                full_ms = track["seconds"] * 1000

                # Skip fatigue: the first song of a session is one the listener picked, so it is
                # rarely skipped; after that, skipping creeps up the longer the session runs.
                fatigue = 0.3 if position == 0 else min(1.7, 1 + 0.03 * position)
                if rng.random() < min(0.92, skip_prob * fatigue):
                    # Most skips happen within a few seconds.
                    ms_played = int(rng.choices(
                        [rng.uniform(800, 4900), rng.uniform(5000, 10000),
                         rng.uniform(10000, 29000), rng.uniform(30000, 60000)],
                        [70, 10, 10, 10])[0])
                    reason_end = "fwdbtn"
                else:
                    ms_played = full_ms - rng.randint(0, 3000)
                    reason_end = "trackdone"

                clock += timedelta(milliseconds=ms_played)   # a play is stamped when it ENDS
                plays.append({
                    "played_at": clock.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "track_uri": f"spotify:track:sample{artist['id']:03d}{artists[artist['id']]['tracks'].index(track):02d}",
                    "track_id": f"sample{artist['id']:03d}",
                    "track_name": track["title"],
                    "artist_name": artist["name"],
                    "album_name": f"{artist['name']} - Sessions",
                    "ms_played": ms_played,
                    "skipped": int(reason_end == "fwdbtn"),
                    "reason_start": reason_start,
                    "reason_end": reason_end,
                    "shuffle": int(shuffle),
                    "platform": platform,
                })
                reason_start = reason_end if reason_end in ("trackdone", "fwdbtn") else "clickrow"
                clock += timedelta(seconds=rng.randint(0, 3))
    return plays


def main() -> None:
    rng = random.Random(SEED)
    artists = make_artists(rng)
    plays = generate_plays(rng, artists)

    SAMPLE_DB.parent.mkdir(parents=True, exist_ok=True)
    if SAMPLE_DB.exists():
        SAMPLE_DB.unlink()

    conn = get_connection(SAMPLE_DB)
    added, skipped = save_plays(conn, plays, source="export")
    conn.execute("VACUUM")  # compact the file
    conn.close()

    size_mb = SAMPLE_DB.stat().st_size / 1e6
    print(f"Wrote {added:,} fake plays ({skipped} duplicates dropped) to {SAMPLE_DB}")
    print(f"File size: {size_mb:.1f} MB   Artists: {ARTIST_COUNT}   Dates: {START} to {END}")


if __name__ == "__main__":
    main()
