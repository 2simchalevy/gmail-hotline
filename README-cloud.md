# Gmail Phone Hotline — Cloud deployment (browser-only, no terminal)

This deploys the hotline permanently to Google Cloud Run, using GitHub +
the Cloud Console web UI to build and deploy — no command line needed.

## What you need already

- A Google Cloud project (`gmail-hotline-509001`) with the Gmail API enabled.
- A Twilio account with a phone number: **+1 (646) 576-7604**.
- A GitHub account.

## Steps

### 1. Push this code to GitHub

Create a new repository on github.com (public or private, doesn't
matter) and upload every file in this folder through GitHub's web
"Add file → Upload files" feature. Do **not** upload `credentials.json`
or `token.json` if you happen to have older copies — those are secrets
and shouldn't go in the repo (the `.gitignore`/`.dockerignore` here
already excludes them).

### 2. Create a Cloud Storage bucket

In Cloud Console → Cloud Storage → **Create bucket**. Any unique name
works, e.g. `gmail-hotline-tokens-<yourname>`. Default settings are fine.
This is where `credentials.json` and `token.json` will live so they
survive Cloud Run restarts.

### 3. Create a "Web application" OAuth client

Your existing OAuth client is type "Desktop app," which only supports
loopback redirects — it won't work for a deployed server. In Cloud
Console → APIs & Services → Credentials → **Create Credentials → OAuth
client ID → Web application**.

Leave "Authorized redirect URIs" empty for now (you'll add it in step 5,
once you know the Cloud Run URL). Download the resulting JSON.

### 4. Upload credentials.json to the bucket

In Cloud Storage, open your new bucket and upload the JSON file from
step 3, renamed to exactly `credentials.json`.

### 5. Deploy to Cloud Run from GitHub

Cloud Console → Cloud Run → **Create service** → "Continuously deploy
from a repository" → connect your GitHub account → select the repo.
Cloud Run will detect the `Dockerfile` automatically.

Under "Variables & Secrets," add an environment variable:
- `GCS_BUCKET` = the bucket name from step 2

Under "Authentication," choose **Allow unauthenticated invocations**
(Twilio needs to reach it without Google login).

Deploy. Once it's live, copy the service URL (looks like
`https://gmail-hotline-xxxxx.a.run.app`).

### 6. Add the redirect URI and OAUTH_REDIRECT_URI

Back in APIs & Services → Credentials → your Web application client →
Authorized redirect URIs, add:

    https://<your-service-url>/oauth2callback

Then back in Cloud Run, edit the service and add a second environment
variable:
- `OAUTH_REDIRECT_URI` = `https://<your-service-url>/oauth2callback`

Redeploy (Cloud Run will prompt you after any env var change).

### 7. One-time Gmail login

Visit `https://<your-service-url>/authorize` in any browser, sign into
the Gmail account you want the hotline to read, and approve access.
You'll see a confirmation page when it's done — this saves `token.json`
into your bucket automatically.

### 8. Point Twilio at your Cloud Run service

Twilio Console → Phone Numbers → your number → Voice Configuration →
"A call comes in" webhook:

    https://<your-service-url>/voice

Method: HTTP POST. Save.

### 9. Test it

Call **+1 (646) 576-7604** from any phone. You should hear your newest
unread email read aloud.

## Notes

- The OAuth consent screen is in "Testing" mode, so the Gmail token
  expires roughly every 7 days — you'll need to revisit `/authorize`
  periodically unless you publish the OAuth consent screen.
- Visiting `/` on the service shows whether Gmail is currently authorized.
