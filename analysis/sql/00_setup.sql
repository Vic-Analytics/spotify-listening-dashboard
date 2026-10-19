-- 00_setup.sql: prepares the data every other query reads. Runs once per connection.
--
-- It builds two things in SQLite's TEMPORARY area (they vanish when the
-- connection closes, so your real tables are never modified):
--
--   play_facts : every play, plus helper columns (local time, hour, weekday,
--                "is this a real play?", "was it skipped?")
--   listens    : play_facts restricted to REAL plays (30 seconds or more)
--
-- utc_offset_seconds() is a small Python function registered into SQLite by
-- queries.py. SQLite has no idea about time zones or daylight saving, so this
-- function says how far your time zone is from UTC at a given moment (e.g.
-- -18000 seconds in Chicago summer). datetime(utc_time, '-18000 seconds') then
-- shifts the time to your local clock.

DROP VIEW  IF EXISTS temp.listens;
DROP TABLE IF EXISTS temp.play_facts;

-- MATERIALIZED tells SQLite to compute `localized` once and store it. Without
-- it, SQLite pastes the datetime(...) expression into every column that uses
-- local_at and recalculates it four times per row, which is much slower.
CREATE TEMP TABLE play_facts AS
WITH localized AS MATERIALIZED (
    SELECT *,
           datetime(played_at, utc_offset_seconds(played_at) || ' seconds') AS local_at
    FROM plays
)
SELECT
    id,
    track_uri,
    track_name,
    artist_name,
    album_name,
    source,
    local_at,                                          -- 'YYYY-MM-DD HH:MM:SS' in your time zone
    date(local_at)                         AS local_date,
    CAST(strftime('%H', local_at) AS INTEGER) AS hour,  -- 0-23
    CAST(strftime('%w', local_at) AS INTEGER) AS dow,   -- 0 = Sunday ... 6 = Saturday

    -- Time actually listened. Export rows have ms_played. API-only rows don't,
    -- so we fall back to the full track length (a good estimate, because the
    -- API only reports tracks you played for 30+ seconds).
    COALESCE(ms_played, duration_ms, 0)    AS ms,

    -- A "real play" follows Spotify's own rule: 30 seconds or more.
    -- API rows (ms_played IS NULL) are real plays by definition.
    CASE WHEN ms_played IS NULL THEN 1
         WHEN ms_played >= 30000 THEN 1
         ELSE 0 END                        AS is_play,

    -- A skip = you pressed the Next button. We use reason_end because, unlike
    -- the export's `skipped` flag, it is filled in for every year.
    CASE WHEN reason_end = 'fwdbtn' THEN 1 ELSE 0 END AS is_skip,

    reason_start,
    reason_end,                                        -- NULL for API-only rows
    shuffle,
    platform
FROM localized;

-- An index makes the date-range filters in every query fast.
CREATE INDEX temp.idx_play_facts_date ON play_facts (local_date);

CREATE TEMP VIEW listens AS
SELECT * FROM play_facts WHERE is_play = 1;
