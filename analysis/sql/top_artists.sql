-- top_artists.sql: most-listened artists, ranked by TIME listened.
-- Parameters: :start, :end (dates), :limit (how many rows).
--
-- GROUP BY collapses all plays of one artist into a single row, and the
-- aggregate functions (COUNT, SUM, MIN, MAX) summarise each group.

SELECT
    artist_name,
    COUNT(*)                        AS plays,
    ROUND(SUM(ms) / 60000.0, 0)     AS minutes,
    COUNT(DISTINCT track_uri)       AS unique_tracks,
    MIN(local_date)                 AS first_heard,
    MAX(local_date)                 AS last_heard
FROM listens
WHERE local_date BETWEEN :start AND :end
GROUP BY artist_name
ORDER BY SUM(ms) DESC
LIMIT :limit;
