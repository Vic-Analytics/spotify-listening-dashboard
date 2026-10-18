-- schema.sql: the shape of our database.
--
-- ONE table, one row per play ("stream"). Both data sources write into it:
--   * the Spotify API collector   (source = 'api')
--   * the Extended History export (source = 'export')
--
-- Why a single flat table instead of separate tracks/artists/albums tables?
-- The export file has no artist IDs, only names, so we can't reliably link
-- to a separate artists table. One wide table keeps every query simple.
--
-- "IF NOT EXISTS" makes this file safe to run every time the program starts.

CREATE TABLE IF NOT EXISTS plays (
    id            INTEGER PRIMARY KEY,   -- auto-numbered by SQLite

    -- WHEN: UTC, always the format 'YYYY-MM-DDTHH:MM:SSZ' (whole seconds).
    -- This is when the play ENDED. Same meaning in the API and the export.
    played_at     TEXT NOT NULL,

    -- WHAT
    track_uri     TEXT NOT NULL,         -- e.g. 'spotify:track:abc123' (never missing)
    track_id      TEXT,                  -- the 'abc123' part (API only)
    track_name    TEXT,
    artist_name   TEXT,                  -- main artist; what Top Artists is based on
    artist_id     TEXT,                  -- API only; the export has none
    all_artists   TEXT,                  -- every credited artist, comma-separated
    album_name    TEXT,

    -- HOW LONG
    duration_ms   INTEGER,               -- full length of the track (API only)
    ms_played     INTEGER,               -- time actually listened (export only)
    skipped       INTEGER,               -- 1 = skipped, 0 = not (export only)

    -- WHERE the play came from: 'playlist', 'album', 'artist' or NULL (API only)
    context_type  TEXT,

    -- HOW it started/ended and on what (export only; NULL for API-only rows).
    -- reason_end values include 'trackdone' (finished) and 'fwdbtn' (skipped).
    reason_start  TEXT,
    reason_end    TEXT,
    shuffle       INTEGER,               -- 1 = shuffle was on
    platform      TEXT,                  -- device family: 'iOS', 'Windows', ...

    -- BOOKKEEPING
    source        TEXT NOT NULL CHECK (source IN ('api', 'export')),
    collected_at  TEXT NOT NULL,         -- when WE saved this row (UTC)

    -- The anti-duplicate rule: you cannot play the same track ending at the
    -- same second twice, so this pair identifies a play. If we try to insert a
    -- second copy, SQLite refuses it (and we tell it to quietly ignore).
    UNIQUE (played_at, track_uri)
);

-- Indexes work like a book's index: they make filtering/grouping on these
-- columns fast once the table has hundreds of thousands of rows.
CREATE INDEX IF NOT EXISTS idx_plays_played_at   ON plays (played_at);
CREATE INDEX IF NOT EXISTS idx_plays_artist_name ON plays (artist_name);
