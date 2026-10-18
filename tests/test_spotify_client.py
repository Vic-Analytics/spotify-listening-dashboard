"""Tests for reading credentials from environment variables."""

import pytest

from collector.spotify_client import _require_env


def test_plain_value_is_returned_unchanged(monkeypatch):
    monkeypatch.setenv("SPOTIFY_TEST_VALUE", "abc123")
    assert _require_env("SPOTIFY_TEST_VALUE") == "abc123"


def test_quotes_and_whitespace_pasted_into_a_secret_are_removed(monkeypatch):
    monkeypatch.setenv("SPOTIFY_TEST_VALUE", "  'abc123'\n")
    assert _require_env("SPOTIFY_TEST_VALUE") == "abc123"


def test_missing_value_gives_a_helpful_error(monkeypatch):
    monkeypatch.delenv("SPOTIFY_TEST_VALUE", raising=False)
    with pytest.raises(RuntimeError, match="SPOTIFY_TEST_VALUE"):
        _require_env("SPOTIFY_TEST_VALUE")
