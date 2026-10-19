-- heatmap.sql: listening by day of week x hour of day (your local time).
-- Parameters: :start, :end (dates).
--
-- Returns one row per (dow, hour) that has any listening. dow: 0 = Sunday ...
-- 6 = Saturday. analysis/metrics.py turns this into a 7 x 24 grid for the chart.

SELECT
    dow,
    hour,
    COUNT(*)                        AS plays,
    ROUND(SUM(ms) / 60000.0, 1)     AS minutes
FROM listens
WHERE local_date BETWEEN :start AND :end
GROUP BY dow, hour
ORDER BY dow, hour;
