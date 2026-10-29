-- 00_setup.sql: prepares the data every other query reads. Runs once per connection.
--
-- It builds two things in SQLite's TEMPORARY area (they vanish when the
-- connection closes, so your real tables are never modified):
--
--   play_facts    : every play, plus helper columns (local time, hour, weekday,
--                   "is this a real play?", "was it skipped?")
--   listens       : play_facts restricted to REAL plays (30 seconds or more)
--   play_sessions : which listening SESSION each play belongs to, and its
--                   position inside that session (see the bottom of this file)
--
-- utc_offset_seconds() is a small Python function registered into SQLite by
-- queries.py. SQLite has no idea about time zones or daylight saving, so this
-- function says how far your time zone is from UTC at a given moment (e.g.
-- -18000 seconds in Chicago summer). datetime(utc_time, '-18000 seconds') then
-- shifts the time to your local clock.

DROP VIEW  IF EXISTS temp.listens;
DROP TABLE IF EXISTS temp.play_sessions;
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
    CAST(strftime('%s', played_at) AS INTEGER) AS end_s, -- when the play ENDED, in UTC seconds (no time zone or DST ambiguity)
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
CREATE INDEX temp.idx_play_facts_artist ON play_facts (artist_name);

CREATE TEMP VIEW listens AS
SELECT * FROM play_facts WHERE is_play = 1;

-- ---------------------------------------------------------------------------
-- Sessions: a new session starts when the gap since the previous play ended is
-- more than 30 minutes (1800 seconds).
--
-- Every play is stamped with when it ENDED, so it started `ms` before that.
-- The gap is "this play's start minus the previous play's end". Plays that
-- follow each other with no pause have a gap of about zero.
--
--   1. timed    : each play's start, and the end of the play before it (LAG)
--   2. flagged  : 1 if this play begins a new session, else 0
--   3. numbered : a running total of those 1s = the session number
--                 (the same running-total trick the streaks query uses)
--
-- All plays count here, including skipped previews: skipping IS part of a
-- session. The 30-minute rule is fixed for the whole dashboard; to try another
-- gap, change 1800 below.
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE play_sessions AS
WITH timed AS (
    SELECT id,
           end_s,
           end_s - ms / 1000.0                            AS start_s,
           LAG(end_s) OVER (ORDER BY end_s, id)           AS prev_end_s
    FROM play_facts
),
flagged AS (
    SELECT id, end_s,
           CASE WHEN prev_end_s IS NULL OR start_s - prev_end_s > 1800 THEN 1 ELSE 0 END AS starts_session
    FROM timed
),
numbered AS (
    SELECT id, end_s,
           SUM(starts_session) OVER (ORDER BY end_s, id)  AS session_id
    FROM flagged
)
SELECT id,
       session_id,
       ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY end_s, id) AS track_number,   -- 1 = first play of the session
       COUNT(*)     OVER (PARTITION BY session_id)                    AS session_tracks
FROM numbered;

CREATE INDEX temp.idx_play_sessions_id ON play_sessions (id);
