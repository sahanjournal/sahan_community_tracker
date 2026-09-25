# Bluesky search authentication setup

Bluesky's `app.bsky.feed.searchPosts` endpoint may return HTTP 403 when called without a session. v0.5.1 supports an app-password session for search while keeping public thread/profile reads unauthenticated.

## 1. Create a Bluesky app password

Sign in to the Bluesky account you want the prototype to use and open:

https://bsky.app/settings/app-passwords

Create a new app password named something like `Sahan citation tracker`.

Use an **app password**, not the account's main password. App passwords can be revoked independently.

## 2. Set environment variables

In the same Terminal window where you will start the dashboard, run:

```bash
export BSKY_HANDLE="your-account.bsky.social"
export BSKY_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"
```

If the account uses a custom handle, use that handle instead.

Do not paste the app password into ChatGPT, source code, GitHub, or the dashboard HTML.

## 3. Start the tracker

```bash
cd ~/Downloads/sahan_community_tracker_v0_5_1
python3 server.py
```

The terminal should report:

```text
Bluesky search auth: configured
```

Then open `http://localhost:8000/api/health`. You should see:

```json
"bluesky_auth_configured": true
```

Now return to `http://localhost:8000`, build an article directory, and click **Find Bluesky mentions**.

## 4. Revoke when needed

You can revoke the app password from Bluesky's App Passwords settings without changing the account's main password.

## Hosting

If you deploy the tracker to Render or another host, add `BSKY_HANDLE` and `BSKY_APP_PASSWORD` as secret environment variables in the host's settings. Do not commit them to the repository.
