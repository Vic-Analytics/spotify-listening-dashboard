-- top_tracks.sql: most-played tracks, ranked by number of real plays.
-- Parameters: :start, :end (dates), :limit (how many rows).
--
-- We group by track_uri (the unique ID) rather than the name, because
-- different songs can share a name. MIN(track_name) just picks that
-- group's name for display.

SELECT
    MIN(track_name)                 AS track_name,
    MIN(artist_name)                AS artist_name,
    COUNT(*)                        AS plays,
    ROUND(SUM(ms) / 60000.0, 0)     AS minutes,
    MAX(local_date)                 AS last_played
FROM listens
WHERE local_date BETWEEN :start AND :end
GROUP BY track_uri
ORDER BY plays DESC, SUM(ms) DESC
LIMIT :limit;
