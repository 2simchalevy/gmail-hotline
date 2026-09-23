"""
server.py

A small Flask app that answers phone calls (via Twilio) and reads the
caller their newest unread Gmail message aloud using text-to-speech.

Two ways to run this:

1. Locally, with ngrok:
       python server.py
       ngrok http 5000
   Set your Twilio number's Voice webhook to https://<ngrok>/voice.

2. Deployed on Cloud Run (see README-cloud.md):
   Set your Twilio number's Voice webhook to https://<cloud-run-url>/voice.

One-time Gmail authorization (works the same way in both cases — just
open it in any browser you're logged into Google with):
       https://<your-server>/authorize
This walks through the Google consent screen and saves the resulting
token wherever gmail_helper.py is configured to store it (locally, or
in the GCS bucket when GCS_BUCKET is set). You only need to do this
once, and again if the token is ever revoked.
"""

from flask import Flask, request, redirect
from werkzeug.middleware.proxy_fix import ProxyFix

from twilio.twiml.voice_response import VoiceResponse

from gmail_helper import (
    get_latest_unread_email,
    mark_as_read,
    build_auth_flow,
    save_credentials_from_flow,
    is_authorized,
)

app = Flask(__name__)
# Cloud Run terminates HTTPS in front of the container and forwards plain
# HTTP internally, setting X-Forwarded-Proto/Host. Without this, Flask
# would think every request is http://, breaking the OAuth redirect URI
# (which must be the https:// URL registered in Google Cloud Console).
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Twilio's built-in Amazon Polly voice. Change to another Polly voice
# name (e.g. "Polly.Matthew") if you'd prefer a different one.
VOICE = "Polly.Joanna"


def _build_email_message():
    """Compose the spoken text for the newest unread email, if any."""
    email = get_latest_unread_email()

    if not email:
        return "You have no new email.", None

    spoken = (
        f"You have a new email from {email['sender']}. "
        f"Subject: {email['subject']}. "
        f"{email['snippet']}"
    )
    return spoken, email["id"]


@app.route("/voice", methods=["GET", "POST"])
def voice():
    """
    TwiML endpoint Twilio calls when someone dials the hotline number.
    Reads back the newest unread email using text-to-speech.
    """
    response = VoiceResponse()

    try:
        spoken_text, message_id = _build_email_message()
    except (FileNotFoundError, RuntimeError) as exc:
        # Gmail credentials.json / token missing, etc.
        response.say(
            "Sorry, the email service is not configured correctly.",
            voice=VOICE,
        )
        app.logger.error(str(exc))
        return str(response)
    except Exception as exc:  # noqa: BLE001 - keep the caller experience graceful
        response.say(
            "Sorry, something went wrong while checking your email. "
            "Please try again later.",
            voice=VOICE,
        )
        app.logger.exception("Error fetching email: %s", exc)
        return str(response)

    response.say(spoken_text, voice=VOICE)

    # Uncomment the next two lines if you'd like the hotline to mark
    # the email as read once it's been played to the caller.
    # if message_id:
    #     mark_as_read(message_id)

    response.say("Goodbye.", voice=VOICE)
    response.hangup()

    return str(response)


@app.route("/", methods=["GET"])
def index():
    status = "authorized" if is_authorized() else "NOT authorized yet — visit /authorize"
    return (
        "Gmail Hotline server is running. "
        f"Gmail status: {status}. "
        "Point your Twilio number's voice webhook at /voice."
    )


@app.route("/authorize", methods=["GET"])
def authorize():
    """
    Start the one-time Gmail OAuth consent flow. Visit this URL in any
    browser signed into the Google account you want to read email from.
    """
    flow = build_auth_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    # Stash the state in a short-lived cookie-free way: Google echoes the
    # state back to us on the callback, so we just pass it through the URL.
    return redirect(auth_url)


@app.route("/oauth2callback", methods=["GET"])
def oauth2callback():
    """Google redirects here after the user approves (or denies) access."""
    state = request.args.get("state")
    error = request.args.get("error")
    if error:
        return f"Authorization failed or was denied: {error}", 400

    flow = build_auth_flow(state=state)
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("OAuth callback failed: %s", exc)
        return f"Authorization failed: {exc}", 400

    save_credentials_from_flow(flow)
    return (
        "Gmail authorization complete! You can close this tab. "
        "Your phone hotline is now able to read your email."
    )


if __name__ == "__main__":
    import os
    # Cloud Run sets the PORT env var; default to 5000 for local runs.
    port = int(os.environ.get("PORT", 5000))
    # debug=True is handy for local development; Cloud Run runs with it off.
    debug = os.environ.get("GCS_BUCKET") is None
    app.run(host="0.0.0.0", port=port, debug=debug)
