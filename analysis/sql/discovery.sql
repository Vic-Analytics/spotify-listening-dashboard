-- discovery.sql: how many NEW artists you hear each month.
-- Parameters: :start, :end (dates).
--
-- "New" = the first month you ever listened to that artist (real plays only).
-- discovery_rate_pct = new artists / all artists you listened to that month.
--
-- Important: first_heard is computed over your WHOLE history, before the date
-- filter. Otherwise, picking "2025 only" would wrongly call every artist you
-- heard in January 2025 new, even ones you have loved since 2018.
--
-- Caveat for your README: your data starts in Nov 2017, so the first months
-- look like 100% discovery. That is the start of the data, not real discovery.

WITH first_heard AS (
    SELECT artist_name, MIN(local_date) AS first_date
    FROM listens
    GROUP BY artist_name
),
monthly_active AS (
    SELECT strftime('%Y-%m-01', local_date) AS month_start,
           COUNT(DISTINCT artist_name)      AS active_artists
    FROM listens
    WHERE local_date BETWEEN :start AND :end
    GROUP BY month_start
),
monthly_new AS (
    SELECT strftime('%Y-%m-01', first_date) AS month_start,
           COUNT(*)                         AS new_artists
    FROM first_heard
    WHERE first_date BETWEEN :start AND :end
    GROUP BY month_start
)
SELECT
    a.month_start,
    a.active_artists,
    COALESCE(n.new_artists, 0)                                           AS new_artists,
    ROUND(100.0 * COALESCE(n.new_artists, 0) / a.active_artists, 1)      AS discovery_rate_pct
FROM monthly_active AS a
LEFT JOIN monthly_new AS n USING (month_start)   -- LEFT JOIN keeps months with 0 new artists
ORDER BY a.month_start;
