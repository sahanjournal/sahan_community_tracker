# Upgrade from v0.4 to v0.5

1. Stop the old server with `Control-C`.
2. Unzip the v0.5 package next to your existing v0.4 folder.
3. Copy the official Sahan logo into the new package if needed:

```bash
cp ~/Downloads/sahan_reddit_mvp_v0_4/assets/sahan-wordmark.png ~/Downloads/sahan_community_tracker_v0_5/assets/sahan-wordmark.png
```

If the v0.4 package does not contain the logo, copy it from your earlier Sahan package instead.

4. Start v0.5:

```bash
cd ~/Downloads/sahan_community_tracker_v0_5
python3 server.py
```

5. Open:

`http://localhost:8000`

6. Search the Sahan archive and select a few stories.
7. Click **Find Bluesky mentions**.
8. Compare the Bluesky results with the **Reddit results** tab.

Bluesky uses the public AppView API and should not require credentials. Reddit may still return HTTP 403/429 until OAuth/Developer Platform access is enabled.
