-- streaks.sql: every run of consecutive listening days, longest first.
-- Parameters: :start, :end (dates).
--
-- The classic "gaps and islands" trick:
--   1. Take each distinct day you listened.
--   2. Number those days 1, 2, 3, ... in order (ROW_NUMBER).
--   3. Subtract that number from the date. Days in an unbroken run all produce
--      the SAME result, because both the date and the row number go up by 1.
--      A gap in the dates makes the result jump, starting a new group.
--   4. GROUP BY that result: each group is one streak.
--
--   date          day number   date - number
--   Oct 01            1          (Sep 30)
--   Oct 02            2          (Sep 30)   <- same group: a 3-day streak
--   Oct 03            3          (Sep 30)
--   Oct 05            4          (Oct 01)   <- gap: new group

WITH days AS (
    SELECT DISTINCT local_date AS day
    FROM listens
    WHERE local_date BETWEEN :start AND :end
),
numbered AS (
    SELECT day,
           julianday(day) - ROW_NUMBER() OVER (ORDER BY day) AS grp
    FROM days
)
SELECT
    MIN(day)   AS streak_start,
    MAX(day)   AS streak_end,
    COUNT(*)   AS days
FROM numbered
GROUP BY grp
ORDER BY days DESC, streak_start DESC;
