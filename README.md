# Gmail Hotline

Dial in on a phone (even a landline or basic phone), and hear your
newest unread Gmail message read aloud.

## What's here

- `gmail_helper.py` — authenticates with Google (OAuth) and fetches
  the newest unread email's subject, sender, and a short snippet.
- `server.py` — a Flask web server with a `/voice` endpoint that
  Twilio calls when someone dials your number. It converts the email
  into speech using Twilio's built-in Amazon Polly voice.
- `requirements.txt` — the Python packages this project needs.

## One-time setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

(Use a virtual environment if you'd like: `python -m venv venv && source venv/bin/activate` first.)

### 2. Add your Google OAuth credentials

You already created a Google Cloud project (`gmail-hotline`), enabled
the Gmail API, and downloaded a Desktop app OAuth Client ID as a JSON
file. Copy that file into this folder and rename it to:

```
credentials.json
```

The first time you run the server (or `python gmail_helper.py`
directly), it will open a browser window asking you to log into the
Google account whose email you want read aloud, and approve access.
After that, a `token.json` file is created automatically here and
reused — you won't need to log in again unless the token expires.

Note: since the OAuth consent screen is in "Testing" mode, Google
expires unverified test tokens after about 7 days, so you may need to
re-approve access periodically until/unless you publish the app.

### 3. Run the server

```bash
python server.py
```

This starts a local web server on port 5000.

### 4. Expose it to the internet with ngrok

Twilio needs a public URL to send call events to. In a separate
terminal:

```bash
ngrok http 5000
```

ngrok will print an https URL like `https://abcd1234.ngrok-free.app`.
Keep this terminal window open — the URL changes each time you
restart ngrok (unless you have a paid ngrok plan with a reserved
domain).

### 5. Point your Twilio number at the server

In the Twilio Console:

1. Go to **Phone Numbers → Manage → Active Numbers**.
2. Click your number: **+1 (646) 576-7604**.
3. Under **Voice Configuration**, set:
   - **A call comes in:** Webhook
   - **URL:** `https://<your-ngrok-subdomain>.ngrok-free.app/voice`
   - **HTTP Method:** POST
4. Save.

### 6. Call your number

Dial +1 (646) 576-7604 from any phone. You should hear your newest
unread email read aloud, then "Goodbye."

## Notes

- The Gmail API scope used is read-only
  (`gmail.readonly`) — this app can never send, delete, or modify
  your email.
- By default the server does **not** mark the email as read after
  playing it, so calling again will read the same message. There's a
  commented-out `mark_as_read(...)` call in `server.py` if you'd
  rather it advance to the next unread email each time.
- Each call currently costs a small per-minute rate charged by
  Twilio (a fraction of a cent per minute on this account), plus the
  ~$1.15/month for renting the phone number itself.
- For a permanent (non-changing) public URL, you'd eventually want
  to deploy `server.py` somewhere always-on (e.g. a small cloud VM
  or platform like Render/Fly.io) instead of relying on ngrok running
  on your own computer.
