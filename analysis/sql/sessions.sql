-- sessions.sql: one row per listening session (see the bottom of 00_setup.sql
-- for how sessions are found).
-- Parameters: :start, :end (dates).
--
-- A session belongs to the date it STARTED on. The date filter is applied after
-- the sessions are built, so a date range never chops a session in two.
--   tracks  = every play in the session, including skipped previews
--   plays   = only the 30+ second ones
--   minutes = wall-clock length: from the first track starting to the last one ending

SELECT
    s.session_id,
    MIN(f.local_at)                                                  AS started_at,
    MIN(f.local_date)                                                AS local_date,
    COUNT(*)                                                         AS tracks,
    SUM(f.is_play)                                                   AS plays,
    SUM(f.is_skip)                                                   AS skips,
    ROUND((MAX(f.end_s) - MIN(f.end_s - f.ms / 1000.0)) / 60.0, 1)   AS minutes
FROM play_facts AS f
JOIN play_sessions AS s ON s.id = f.id
GROUP BY s.session_id
HAVING MIN(f.local_date) BETWEEN :start AND :end
ORDER BY s.session_id;
