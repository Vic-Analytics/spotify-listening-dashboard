-- summary.sql: the headline numbers (one row).
-- Parameters: :start and :end are dates like '2025-01-01' (your local dates).
--
-- A CTE (WITH ... AS) is a named, temporary result you can reuse below.
-- Here `in_range` is "real plays inside the chosen dates".

WITH in_range AS (
    SELECT * FROM listens
    WHERE local_date BETWEEN :start AND :end
),
top_artist AS (                       -- the artist with the most listening time
    SELECT artist_name, SUM(ms) AS ms
    FROM in_range
    GROUP BY artist_name
    ORDER BY SUM(ms) DESC
    LIMIT 1
)
SELECT
    COUNT(*)                                   AS plays,
    ROUND(SUM(ms) / 60000.0, 0)                AS minutes_listened,
    COUNT(DISTINCT artist_name)                AS unique_artists,
    COUNT(DISTINCT track_uri)                  AS unique_tracks,
    COUNT(DISTINCT local_date)                 AS active_days,
    MIN(local_date)                            AS first_date,
    MAX(local_date)                            AS last_date,
    (SELECT artist_name FROM top_artist)       AS top_artist,
    ROUND((SELECT ms FROM top_artist) / 60000.0, 0) AS top_artist_minutes
FROM in_range;
