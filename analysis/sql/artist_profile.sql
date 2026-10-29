-- artist_profile.sql: one row of facts about a single artist. All-time.
-- Parameters: :artist (exact artist name).
--
--   starts           every time a track by them began (including quick skips)
--   plays            the ones that lasted 30+ seconds
--   share_pct        their share of ALL your listening time
--   minutes_rank     1 = your most-listened artist
--   skip_rate_pct    how often you pressed Next on their tracks
--   period_skip_pct  your skip rate on EVERYTHING between their first and last play,
--                    so you can tell "I skip them" from "I skipped everything then".
--                    (Both skip rates only cover export rows.)
-- An artist with no plays returns plays = 0 and empty values.

WITH mine AS (
    SELECT * FROM listens WHERE artist_name = :artist
),
ranks AS (
    SELECT artist_name, RANK() OVER (ORDER BY SUM(ms) DESC) AS minutes_rank
    FROM listens
    GROUP BY artist_name
)
SELECT
    MIN(local_date)                                                             AS first_heard,
    MAX(local_date)                                                             AS last_heard,
    COUNT(*)                                                                    AS plays,
    (SELECT COUNT(*) FROM play_facts WHERE artist_name = :artist)               AS starts,
    ROUND(SUM(ms) / 60000.0, 0)                                                 AS minutes,
    COUNT(DISTINCT local_date)                                                  AS active_days,
    COUNT(DISTINCT track_uri)                                                   AS tracks,
    ROUND(100.0 * SUM(ms) / (SELECT SUM(ms) FROM listens), 2)                   AS share_pct,
    (SELECT minutes_rank FROM ranks WHERE artist_name = :artist)                AS minutes_rank,
    (SELECT ROUND(100.0 * AVG(is_skip), 1) FROM play_facts
      WHERE artist_name = :artist AND reason_end IS NOT NULL)                   AS skip_rate_pct,
    (SELECT ROUND(100.0 * AVG(is_skip), 1) FROM play_facts
      WHERE reason_end IS NOT NULL
        AND local_date BETWEEN (SELECT MIN(local_date) FROM mine)
                           AND (SELECT MAX(local_date) FROM mine))              AS period_skip_pct
FROM mine;
