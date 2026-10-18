"""
spotify_client.py - builds a logged-in Spotify connection.

Every other script in the project (the hourly collector, the playlist
fetcher, ...) calls get_spotify_client() instead of doing its own login.
Keeping login in ONE place means there is only one thing to fix if it breaks.

How Spotify login works (OAuth, simplified):
  1. ONE time, you click "Agree" in your browser (collector/login.py does this).
     Spotify then gives us a REFRESH TOKEN: a long-lived password that only
     works for our app and only for the permissions ("scopes") we asked for.
  2. After that, no browser is needed. We trade the refresh token for a
     short-lived ACCESS TOKEN (valid ~1 hour) each time we run.
     Spotipy does this swap automatically.

That's why the refresh token goes in .env (and later in GitHub Secrets):
it lets an unattended script, like GitHub Actions, log in as you.
"""

import os
from pathlib import Path

import spotipy
from dotenv import load_dotenv
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyOAuth

# The project root is the folder above this file's folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# Read .env into environment variables. If .env doesn't exist (e.g. on
# GitHub Actions) this quietly does nothing, and we use the variables that
# GitHub Secrets provide instead. The same code works in both places.
load_dotenv(ENV_PATH)

# Permissions we ask the user for. We ask for the minimum we need.
#   user-read-recently-played -> the last 50 tracks played
#   user-top-read             -> top artists / tracks
#   playlist-read-private     -> your playlists
SCOPES = "user-read-recently-played user-top-read playlist-read-private"

# Spotify no longer accepts "localhost" as a redirect address; it must be the
# loopback IP 127.0.0.1. This must match what you typed in the dashboard.
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"


def _require_env(name: str) -> str:
    """Return an environment variable, or stop with a helpful message."""
    # Strip spaces/newlines AND stray quotes: values pasted into GitHub Secrets
    # often arrive wrapped in quotes or with a trailing newline.
    value = os.getenv(name, "").strip().strip("'\"").strip()
    if not value:
        raise RuntimeError(
            f"Missing {name}. Open your .env file and fill it in "
            f"(see .env.example for what each value is)."
        )
    return value


def get_spotify_client() -> spotipy.Spotify:
    """
    Return a Spotify client that logs in using the saved refresh token.
    Never opens a browser, so it is safe to run unattended.
    """
    client_id = _require_env("SPOTIFY_CLIENT_ID")
    client_secret = _require_env("SPOTIFY_CLIENT_SECRET")
    refresh_token = _require_env("SPOTIFY_REFRESH_TOKEN")
    # "or" also falls back to the default when the variable exists but is blank.
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI") or DEFAULT_REDIRECT_URI

    # Spotipy normally saves tokens to a ".cache" file. Instead we hand it a
    # token held in memory. "expires_at: 0" says "this access token is already
    # expired", which makes Spotipy immediately swap our refresh token for a
    # fresh access token. No files written, nothing left lying around.
    starting_token = {
        "access_token": "",
        "token_type": "Bearer",
        "expires_at": 0,
        "refresh_token": refresh_token,
        "scope": SCOPES,
    }

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPES,
        cache_handler=MemoryCacheHandler(token_info=starting_token),
        open_browser=False,  # if something is wrong, fail instead of popping up a browser
    )
    return spotipy.Spotify(auth_manager=auth_manager)
