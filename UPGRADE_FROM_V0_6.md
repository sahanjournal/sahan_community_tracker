# Upgrade from v0.6 to v0.6.1

v0.6.1 fixes topic/reporter dropdown initialization.

## What changed

- Topics and reporters now load independently. A failure in one endpoint no longer prevents the other dropdown from populating.
- Reporter loading now falls back to author metadata embedded in published Sahan posts when WordPress restricts the public `/users` endpoint.
- The dashboard reports how many topics and reporters were loaded, or shows a specific metadata warning.

## Deploy

Replace the v0.6 files in the repository with the v0.6.1 files, commit/push, and redeploy the Render service.

Then check:

- `/api/health`
- `/api/categories`
- `/api/users`

The latter two should return JSON arrays.
