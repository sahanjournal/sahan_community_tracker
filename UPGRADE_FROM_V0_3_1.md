# Upgrade from v0.3.1

1. Stop the old server with `Control-C`.
2. Unzip v0.4 next to the old folder.
3. Copy your official logo from the old package:

```bash
cp ~/Downloads/sahan_reddit_mvp_v0_3_1/assets/sahan-wordmark.png ~/Downloads/sahan_reddit_mvp_v0_4/assets/sahan-wordmark.png
```

4. Start v0.4:

```bash
cd ~/Downloads/sahan_reddit_mvp_v0_4
python3 server.py
```

5. Open `http://localhost:8000`.
6. Search for a known Sahan issue, select a few stories, and click **Find Reddit mentions**.

If archive search still reports a 502, the updated dashboard will display the underlying connection detail returned by `server.py`. If Reddit discovery reports an HTTP 403/429, use the manual Reddit links for now and move the next build to Reddit's Developer Platform.
