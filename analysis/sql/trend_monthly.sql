-- trend_monthly.sql: minutes listened per calendar month.
-- Parameters: :start, :end (dates).
--
-- strftime('%Y-%m-01', d) rewrites any date as the first day of its month,
-- so every play in October 2026 groups under '2026-10-01'.

SELECT
    strftime('%Y-%m-01', local_date)  AS month_start,
    COUNT(*)                          AS plays,
    ROUND(SUM(ms) / 60000.0, 1)       AS minutes,
    COUNT(DISTINCT local_date)        AS active_days
FROM listens
WHERE local_date BETWEEN :start AND :end
GROUP BY month_start
ORDER BY month_start;
