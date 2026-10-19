-- skips_trend.sql: share of plays ended with the Next button, per month.
-- Parameters: :start, :end (dates).
--
-- Uses play_facts (ALL plays, including ones under 30 seconds), because skips
-- mostly happen in the first few seconds, and `listens` would hide them.
-- Only export rows are used: API-only rows have no reason_end, so we cannot
-- tell whether they were skipped. AVG(is_skip) of a 0/1 column = the share of 1s.

SELECT
    strftime('%Y-%m-01', local_date)    AS month_start,
    COUNT(*)                            AS plays,
    SUM(is_skip)                        AS skips,
    ROUND(100.0 * AVG(is_skip), 1)      AS skip_rate_pct
FROM play_facts
WHERE reason_end IS NOT NULL
  AND local_date BETWEEN :start AND :end
GROUP BY month_start
ORDER BY month_start;
