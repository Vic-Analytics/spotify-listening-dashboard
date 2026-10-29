-- artist_tracks.sql: one artist's tracks, most-played first. All-time.
-- Parameters: :artist (exact artist name), :limit (how many rows).
--
-- Grouped by track_uri (the unique ID). Tracks that never reached 30 seconds are
-- left out (HAVING plays > 0). `starts` also counts the quick skips.
-- AVG ignores NULL, so API-only rows (reason_end unknown) don't count as "not skipped".

SELECT
    MIN(track_name)                                                  AS track_name,
    SUM(is_play)                                                     AS plays,
    COUNT(*)                                                         AS starts,
    ROUND(SUM(CASE WHEN is_play = 1 THEN ms ELSE 0 END) / 60000.0, 0) AS minutes,
    ROUND(100.0 * AVG(CASE WHEN reason_end IS NOT NULL THEN is_skip END), 1) AS skip_rate_pct,
    MIN(CASE WHEN is_play = 1 THEN local_date END)                   AS first_played,
    MAX(CASE WHEN is_play = 1 THEN local_date END)                   AS last_played
FROM play_facts
WHERE artist_name = :artist
GROUP BY track_uri
HAVING SUM(is_play) > 0
ORDER BY plays DESC, minutes DESC, track_name
LIMIT :limit;
