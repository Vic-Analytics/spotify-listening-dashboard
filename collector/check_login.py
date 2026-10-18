"""
check_login.py - confirms the saved refresh token works with NO browser.

Run it with:
    python -m collector.check_login

This tests exactly the login path that GitHub Actions will use later
(credentials from environment variables, no human clicking "Agree"),
so if this passes locally, the hourly automation can log in too.
"""

from collector.spotify_client import get_spotify_client


def main() -> None:
    sp = get_spotify_client()

    # Cheapest possible request: "who am I?"
    me = sp.current_user()
    print(f"Connected as: {me['display_name']} (id: {me['id']})")

    # Also confirm the "recently played" permission was granted. limit=1 keeps it tiny.
    recent = sp.current_user_recently_played(limit=1)
    count = len(recent["items"])
    print(f"'Recently played' endpoint works ({count} item returned).")
    print("Phase 1 complete!")


if __name__ == "__main__":
    main()
