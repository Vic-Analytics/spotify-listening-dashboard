-- skips_by_context.sql: does skip behaviour change by device or shuffle?
-- Parameters: :start, :end (dates).

SELECT
    platform,
    CASE WHEN shuffle = 1 THEN 'shuffle on' ELSE 'shuffle off' END AS shuffle_mode,
    COUNT(*)                          AS plays,
    SUM(is_skip)                      AS skips,
    ROUND(100.0 * AVG(is_skip), 1)    AS skip_rate_pct
FROM play_facts
WHERE reason_end IS NOT NULL
  AND local_date BETWEEN :start AND :end
GROUP BY platform, shuffle_mode
ORDER BY plays DESC;
