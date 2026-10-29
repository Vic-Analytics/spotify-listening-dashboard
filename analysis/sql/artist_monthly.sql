-- artist_monthly.sql: one artist's minutes listened per month. All-time.
-- Parameters: :artist (exact artist name).
-- Same shape as trend_monthly.sql, so the same chart and gap-filling code work.

SELECT
    strftime('%Y-%m-01', local_date)  AS month_start,
    COUNT(*)                          AS plays,
    ROUND(SUM(ms) / 60000.0, 1)       AS minutes
FROM listens
WHERE artist_name = :artist
GROUP BY month_start
ORDER BY month_start;
