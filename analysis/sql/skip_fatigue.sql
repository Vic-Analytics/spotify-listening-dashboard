-- skip_fatigue.sql: do you skip more the longer a session goes on?
-- Parameters: :start, :end (dates).
--
-- Skip rate by a play's position inside its session (track 1, tracks 2-3, ...).
-- Only plays from the export are used, because API-only rows cannot tell us
-- whether a track was skipped.
--
-- Two series are returned, because the first one alone can mislead:
--   'All sessions'            long sessions contribute to the late buckets and short
--                             ones don't, so the mix of sessions changes along the chart.
--   'Sessions of 20+ tracks'  the SAME sessions appear in every bucket up to the 20th
--                             track, so any change there is not a change in who is counted.
-- The 1st track is usually a song you picked yourself, so it is rarely skipped.

WITH scoped AS (
    SELECT f.is_skip, s.track_number, s.session_tracks
    FROM play_facts AS f
    JOIN play_sessions AS s ON s.id = f.id
    WHERE f.reason_end IS NOT NULL
      AND f.local_date BETWEEN :start AND :end
),
bucketed AS (
    SELECT is_skip, session_tracks,
           CASE WHEN track_number =  1 THEN '1. 1'
                WHEN track_number <= 3 THEN '2. 2-3'
                WHEN track_number <= 6 THEN '3. 4-6'
                WHEN track_number <= 10 THEN '4. 7-10'
                WHEN track_number <= 20 THEN '5. 11-20'
                WHEN track_number <= 40 THEN '6. 21-40'
                ELSE                         '7. 41+' END AS position_bucket
    FROM scoped
)
SELECT 'All sessions' AS scope, position_bucket,
       COUNT(*) AS plays, SUM(is_skip) AS skips, ROUND(100.0 * AVG(is_skip), 1) AS skip_rate_pct
FROM bucketed
GROUP BY position_bucket
UNION ALL
SELECT 'Sessions of 20+ tracks', position_bucket,
       COUNT(*), SUM(is_skip), ROUND(100.0 * AVG(is_skip), 1)
FROM bucketed
WHERE session_tracks >= 20
GROUP BY position_bucket
ORDER BY scope, position_bucket;
