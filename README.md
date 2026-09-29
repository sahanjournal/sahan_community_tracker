# Sahan Journal Community Citation Tracker — v0.5

v0.5.1 folds Bluesky into the existing article-directory and Reddit dashboard.

## What is live

1. Search Sahan Journal's public WordPress archive.
2. Select the stories you want to monitor.
3. Click **Find Reddit mentions** or **Find Bluesky mentions**.
4. Review returned posts and audience responses inside the dashboard.

### Reddit

The Reddit collector still uses the low-volume public JSON adapter from v0.4. It can encounter Reddit HTTP 403/429 responses until the project is moved to approved OAuth/Developer Platform access.

Known Sahan Reddit accounts:

- `u/sahan-journal`
- `u/sahanjournalnews`

Posts from those accounts are classified as **publisher distribution**. Comments from other Redditors on those threads are still surfaced as audience/community evidence.

### Bluesky

Bluesky thread/profile reads use the public AppView API. Post search may return HTTP 403 without a session, so v0.5.1 supports `BSKY_HANDLE` + `BSKY_APP_PASSWORD` for authenticated search through the account PDS.

For each selected Sahan story the server searches up to three query forms:

- exact Sahan article URL;
- exact article headline;
- `"Sahan Journal"` plus distinctive headline terms.

It then deduplicates posts, scores likely matches, and fetches replies for strong matches or Sahan-owned posts.

Known Sahan Bluesky account:

- `@sahanjournal.bsky.social`

Posts from that account are classified as **publisher distribution**. Replies by other Bluesky users are surfaced separately as audience/community evidence.

## Run locally

```bash
export BSKY_HANDLE="sahanjournal.bsky.social"
export BSKY_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"
cd sahan_community_tracker_v0_5
python3 server.py
```

Open:

`http://localhost:8000`

For reliable Bluesky post search, configure a Bluesky app password using `BSKY_HANDLE` and `BSKY_APP_PASSWORD`. Never use or store the account's main password. No Reddit password or cookie is used.

## Suggested test

1. Search the archive for `Northern Iron`, `Operation Metro Surge`, or another body of coverage you know well.
2. Select 3–5 stories.
3. Click **Find Bluesky mentions**.
4. Review independent posts, Sahan-posted threads, and surfaced replies.
5. Run the same directory through Reddit for comparison.
6. Verify promising matches before treating them as impact evidence.

## Files

- `dashboard.html` — combined Reddit + Bluesky interface.
- `server.py` — WordPress proxy plus Reddit and Bluesky discovery endpoints.
- `bluesky_collector.py` — standalone command-line Bluesky collector retained for batch use.
- `UPGRADE_FROM_V0_4.md` — upgrade steps.
- `assets/` — place Sahan's official wordmark at `assets/sahan-wordmark.png`.

## Prototype limitations

- Reddit public search may return 403/429 until OAuth access is wired in.
- Bluesky search is query-based, so it can miss posts that paraphrase a story without naming Sahan or linking the article.
- Relevance scoring is rules-based in v0.5. Human verification remains the final step.
- Saved evidence is not yet written to a shared database; results are session output in the dashboard.

The next product step is a shared evidence ledger with **Keep / Reject / Notes** controls, followed by scheduled monitoring of saved directories.

## Bluesky 403 fix

See `BLUESKY_AUTH_SETUP.md`. The app password belongs in environment variables, not in the code or dashboard.
