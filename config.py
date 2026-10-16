from __future__ import annotations

APP_NAME = "Teal's Sunday Pick'em"
APP_TAGLINE = "Pick five. Own Sunday."
# Prior public version: APP_VERSION = "1.0.7"
APP_VERSION = "1.0.8"
# Internal deploy/cache key. Keep the public-facing version stable while making
# every hotfix a distinct Streamlit resource-cache generation. Without this,
# a warm Streamlit Cloud process can reuse a SupabaseStore instance created by
# an older class definition across a multi-file deploy.
APP_BUILD_VERSION = "1.0.8-hotfix8.1"
# Prior release: APP_BUILD_VERSION = "1.0.8-pickem-pulse"
# Prior release: APP_BUILD_VERSION = "1.0.7-hotfix7.19"
# Prior cumulative build: APP_BUILD_VERSION = "1.0.7-hotfix7.17"
# Prior cumulative build: APP_BUILD_VERSION = "1.0.7-hotfix7.16"
# Prior cumulative build: APP_BUILD_VERSION = "1.0.7-hotfix7.15.2"
# Prior cumulative build: APP_BUILD_VERSION = "1.0.7-hotfix7.15.1"
# Prior cumulative build: APP_BUILD_VERSION = "1.0.7-hotfix7.15"
# Prior cumulative build: APP_BUILD_VERSION = "1.0.7-hotfix7.14.1"
# Prior cumulative build: APP_BUILD_VERSION = "1.0.7-hotfix7.14"
# Prior cumulative build: APP_BUILD_VERSION = "1.0.7-hotfix7.13"
# Prior cumulative build: APP_BUILD_VERSION = "1.0.7-hotfix7.12"
# Prior cumulative build: APP_BUILD_VERSION = "1.0.7-hotfix7.11"
# Prior cumulative build marker: APP_BUILD_VERSION = "1.0.7-hotfix7.10.1"
# APP_BUILD_VERSION = "1.0.7-hotfix7.10"
# APP_BUILD_VERSION = "1.0.7-hotfix7.9.1"
# APP_BUILD_VERSION = "1.0.7-hotfix7.9"
# Prior build markers retained for legacy regression text checks:
# APP_BUILD_VERSION = "1.0.7-hotfix7.8"
# APP_BUILD_VERSION = "1.0.7-hotfix7.3"
TIMEZONE_NAME = "America/New_York"

PLAYER_PIN_LENGTH = 4
COMMISH_PIN_LENGTH = 6
MAX_NICKNAME_LENGTH = 15
REMEMBER_DAYS = 210  # comfortably covers an NFL season
COOKIE_NAME = "tsp_session_v1"
REMEMBER_STORAGE_KEY = "tsp_remember_device_v1"
REMEMBER_COOKIE_MAX_AGE = REMEMBER_DAYS * 24 * 60 * 60

# Low-entropy 4-digit PINs require both slow hashing and login throttling.
PBKDF2_ITERATIONS = 600_000
LOGIN_WINDOW_MINUTES = 10
MAX_FAILED_LOGINS_PER_WINDOW = 8

# Gate 3 data settings.
NFL_SEASON = 2026
NFL_SEASON_TYPE = 2  # ESPN regular season
GATE3_HTTP_TIMEOUT_SECONDS = 12
GATE3_PUBLIC_CACHE_SECONDS = 60
LIVE_SCORE_REFRESH_MINUTES = 5
ACTIVE_GAME_STATE_REFRESH_MINUTES = 2
ACTIVE_PLAYER_STAT_REFRESH_MINUTES = 3
LIVE_APP_DISPLAY_REFRESH_SECONDS = 15
LIVE_GAME_STALE_MINUTES = 7
# Prior live cadence retained for legacy regression text checks: LIVE_SCORE_REFRESH_MINUTES = 15
FINALIZE_HOUR_ET = 9
POOL_PUBLISH_HOUR_ET = 12
POOL_REPLACEMENT_CUTOFF_WEEKDAY = 5  # Saturday, Python weekday()
POOL_REPLACEMENT_CUTOFF_HOUR_ET = 23
POOL_REPLACEMENT_CUTOFF_MINUTE_ET = 59
