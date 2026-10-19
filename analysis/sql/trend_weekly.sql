-- trend_weekly.sql: minutes listened per week (weeks start on Monday).
-- Parameters: :start, :end (dates).
--
-- date(d, 'weekday 0', '-6 days'):
--   'weekday 0' moves d forward to the next Sunday (or stays if it is Sunday),
--   then '-6 days' goes back to the Monday of that same week.
-- Weeks with no listening at all are missing here; the charts fill them with 0.

SELECT
    date(local_date, 'weekday 0', '-6 days')  AS week_start,
    COUNT(*)                                  AS plays,
    ROUND(SUM(ms) / 60000.0, 1)               AS minutes
FROM listens
WHERE local_date BETWEEN :start AND :end
GROUP BY week_start
ORDER BY week_start;
