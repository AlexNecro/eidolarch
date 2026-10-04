# Eidolarch 2.3.5

Localization cache hotfix.

## Fixed
- Duplicate workspace labels no longer render as em dashes after upgrades.
- Locale JSON requests are versioned with the client release.
- Locale API responses explicitly disable browser caching.
- Service worker shell cache bumped for 2.3.5.

This fixes stale 2.3.x locale files being combined with a newer JavaScript bundle.
