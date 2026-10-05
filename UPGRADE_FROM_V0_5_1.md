# Upgrade from v0.5.1 to v0.6

v0.6 adds newsroom-level corpus controls without changing your Bluesky authentication setup.

## New controls

- Topic / section selector populated from Sahan's WordPress categories.
- Reporter selector populated from Sahan's WordPress authors.
- Published-timeframe presets: last 30 days, 90 days, 6 months, 12 months, year to date, previous calendar year, or custom dates.
- A global **Include comments & replies** switch. When off, Reddit and Bluesky perform a posts-only scan and do not fetch thread discussion.

## Upgrade

1. Stop the old server with `Control-C`.
2. Replace the old folder with this v0.6 package, or unzip it beside v0.5.1.
3. Preserve your existing Bluesky environment variables:
   - `BSKY_HANDLE`
   - `BSKY_APP_PASSWORD`
4. Start the app:

```bash
cd ~/Downloads/sahan_community_tracker_v0_6
python3 server.py
```

5. Open `http://localhost:8000`.

If you deploy through Render, push the v0.6 files to the same GitHub repository and redeploy. Your existing Render environment variables can remain unchanged.
