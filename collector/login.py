"""
login.py - the ONE-TIME interactive login.

Run it from the project folder with:
    python -m collector.login

What happens:
  1. Your browser opens on Spotify's "Do you allow this app?" page.
  2. You click Agree. Spotify redirects to http://127.0.0.1:8888/callback,
     where a tiny temporary web server (started by Spotipy) catches the
     one-time code in the address.
  3. Spotipy swaps that code for tokens.
  4. We save the REFRESH TOKEN into your .env file and run a quick test.

You only need to run this again if you change the scopes in spotify_client.py
or revoke the app's access on spotify.com/account/apps.
"""

import os

import spotipy
from dotenv import set_key
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyOAuth

# Importing this module also loads .env (see spotify_client.py).
from collector.spotify_client import (
    DEFAULT_REDIRECT_URI,
    ENV_PATH,
    SCOPES,
    _require_env,
)


def main() -> None:
    if not ENV_PATH.exists():
        raise SystemExit(
            f"No .env file found at {ENV_PATH}.\n"
            "Copy .env.example to .env and fill in SPOTIFY_CLIENT_ID and "
            "SPOTIFY_CLIENT_SECRET first."
        )

    # A memory cache holds the token only while this script runs, so we control
    # exactly where the refresh token ends up (.env), not a hidden .cache file.
    cache = MemoryCacheHandler()
    auth_manager = SpotifyOAuth(
        client_id=_require_env("SPOTIFY_CLIENT_ID"),
        client_secret=_require_env("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI") or DEFAULT_REDIRECT_URI,
        scope=SCOPES,
        cache_handler=cache,
        open_browser=True,
    )

    # Making any request triggers the browser login if we have no token yet.
    sp = spotipy.Spotify(auth_manager=auth_manager)
    me = sp.current_user()

    # After the login above, the cache holds the tokens Spotify gave us.
    refresh_token = cache.get_cached_token()["refresh_token"]
    # quote_mode="never" writes the bare token. By default set_key wraps values in
    # quotes, and copying that quoted text into a GitHub secret breaks the login.
    set_key(str(ENV_PATH), "SPOTIFY_REFRESH_TOKEN", refresh_token, quote_mode="never")

    print(f"Logged in as: {me['display_name']}")
    print(f"Refresh token saved to {ENV_PATH}")
    print("Next, run:  python -m collector.check_login")


if __name__ == "__main__":
    main()
