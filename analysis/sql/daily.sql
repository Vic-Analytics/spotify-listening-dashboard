-- daily.sql: listening per calendar day. It feeds the calendar heatmap.
-- Parameters: :start, :end (dates).
-- Days with no listening are absent; analysis/metrics.py fills them in.

SELECT
    local_date,
    COUNT(*)                        AS plays,
    ROUND(SUM(ms) / 60000.0, 1)     AS minutes
FROM listens
WHERE local_date BETWEEN :start AND :end
GROUP BY local_date
ORDER BY local_date;
