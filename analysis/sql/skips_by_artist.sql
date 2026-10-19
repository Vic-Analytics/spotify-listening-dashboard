-- skips_by_artist.sql: which artists do you skip most (and least)?
-- Parameters: :start, :end (dates), :min_plays (ignore artists with few plays).
--
-- HAVING is WHERE for groups: it filters AFTER GROUP BY has counted things.
-- The minimum matters because an artist you played twice and skipped once would
-- otherwise show a meaningless 50% skip rate.

SELECT
    artist_name,
    COUNT(*)                          AS plays,
    SUM(is_skip)                      AS skips,
    ROUND(100.0 * AVG(is_skip), 1)    AS skip_rate_pct
FROM play_facts
WHERE reason_end IS NOT NULL
  AND local_date BETWEEN :start AND :end
GROUP BY artist_name
HAVING COUNT(*) >= :min_plays
ORDER BY skip_rate_pct DESC, plays DESC;
