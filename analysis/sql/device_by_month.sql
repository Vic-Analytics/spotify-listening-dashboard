-- device_by_month.sql: listening per device (platform) per calendar month.
-- Parameters: :start, :end (dates).
--
-- Only plays that carry a platform are counted. That is every play from the
-- Spotify export, plus API plays the export has enriched; a play known only from
-- the API has no platform and is left out. analysis/metrics.py turns minutes into
-- each device's share of the month.

SELECT
    strftime('%Y-%m-01', local_date)  AS month_start,
    platform,
    COUNT(*)                          AS plays,
    ROUND(SUM(ms) / 60000.0, 1)       AS minutes
FROM listens
WHERE platform IS NOT NULL
  AND local_date BETWEEN :start AND :end
GROUP BY month_start, platform
ORDER BY month_start, platform;
