-- shuffle_by_month.sql: share of real plays that happened with shuffle on, per month.
-- Parameters: :start, :end (dates).
--
-- `shuffle` is 1 or 0 for export plays and NULL when unknown (API-only plays), so
-- unknown plays are left out rather than counted as "off". AVG of a 0/1 column is
-- the share of 1s. Months with fewer than 20 known plays are dropped: a percentage
-- of a handful of plays swings wildly and says nothing.

SELECT
    strftime('%Y-%m-01', local_date)  AS month_start,
    COUNT(*)                          AS plays,
    SUM(shuffle)                      AS shuffle_plays,
    ROUND(100.0 * AVG(shuffle), 1)    AS shuffle_pct
FROM listens
WHERE shuffle IS NOT NULL
  AND local_date BETWEEN :start AND :end
GROUP BY month_start
HAVING COUNT(*) >= 20
ORDER BY month_start;
