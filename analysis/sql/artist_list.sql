-- artist_list.sql: every artist you have listened to, biggest first. It fills
-- the artist picker on the deep-dive page. No date parameters: the picker
-- always offers your whole history.
--
-- Artists are matched by NAME, because the Spotify export only gives names.
-- On a collaboration, only the track's main artist is credited.

SELECT
    artist_name,
    COUNT(*)                        AS plays,
    ROUND(SUM(ms) / 60000.0, 0)     AS minutes
FROM listens
WHERE artist_name IS NOT NULL AND artist_name <> ''
GROUP BY artist_name
ORDER BY SUM(ms) DESC, artist_name;
