-- skip_timing.sql: how quickly do you skip? Skips bucketed by listening time.
-- Parameters: :start, :end (dates).
--
-- CASE WHEN works like if / elif / else. The numeric prefix in each label
-- ("1.", "2.", ...) only exists so ORDER BY sorts the buckets in the right order.

SELECT
    CASE WHEN ms <  5000 THEN '1. under 5 sec'
         WHEN ms < 10000 THEN '2. 5-10 sec'
         WHEN ms < 30000 THEN '3. 10-30 sec'
         WHEN ms < 60000 THEN '4. 30-60 sec'
         ELSE                 '5. over 60 sec' END   AS skipped_after,
    COUNT(*)                                         AS skips,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_skips
FROM play_facts
WHERE is_skip = 1
  AND local_date BETWEEN :start AND :end
GROUP BY skipped_after
ORDER BY skipped_after;
