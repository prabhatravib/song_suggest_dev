from flask import Blueprint, session, request, redirect, render_template, url_for
from spotipy.oauth2 import SpotifyPKCE
import os
import secrets
from urllib.parse import urlencode, quote

from analytics import store_login_data

spotify_auth = Blueprint("spotify_auth", __name__)

def create_auth_manager():
    """
    Create the Spotify Authentication Manager with PKCE.
    """
    return SpotifyPKCE(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        redirect_uri=os.getenv(
            "SPOTIFY_REDIRECT_URI",
            "https://songsuggest.onrender.com/callback"
        ),
        scope="playlist-read-private"
    )

def detect_device():
    """
    Detect if the request comes from a mobile or desktop device.
    """
    ua = request.headers.get("User-Agent", "").lower()
    if any(m in ua for m in ["mobile", "android", "iphone", "ipad"]):
        return "mobile"
    return "desktop"

def build_android_intent(inapp_url, fallback_url):
    """
    Construct an Android intent URI that opens the Spotify app (or falls back).
    """
    params = {
        "scope": "playlist-read-private",
        "response_type": "code",
        "redirect_uri": os.getenv(
            "SPOTIFY_REDIRECT_URI",
            "https://songsuggest.onrender.com/callback"
        ),
        "client_id": os.getenv("SPOTIFY_CLIENT_ID"),
        "state": session.get("spotify_csrf_token")
    }
    qs = urlencode(params)
    intent = (
        f"intent://accounts.spotify.com/inapp-authorize?{qs}"
        "#Intent;"
        "scheme=https;"
        "package=com.spotify.music;"
        f"S.browser_fallback_url={quote(fallback_url)};"
        "end"
    )
    return intent

@spotify_auth.route("/spotify_auth", methods=["GET", "POST"])
def spotify_auth_route():
    """
    Starts the Spotify OAuth flow.
    """
    try:
        csrf_token = secrets.token_hex(16)
        session["spotify_csrf_token"] = csrf_token

        auth_manager = create_auth_manager()
        auth_url     = auth_manager.get_authorize_url(state=csrf_token)
        inapp_url    = auth_url.replace("/authorize?", "/inapp-authorize?")

        session["code_verifier"]  = auth_manager.code_verifier
        session["code_challenge"] = auth_manager.code_challenge
        session.modified          = True

        ua = request.headers.get("User-Agent", "").lower()
        if "android" in ua and "mobile" in ua:
            return redirect(build_android_intent(inapp_url, auth_url))
        elif any(ios in ua for ios in ("iphone", "ipad", "ipod")):
            return redirect(inapp_url)
        else:
            return redirect(auth_url)

    except Exception as e:
        print(f"Error starting Spotify auth: {e}")
        return render_template("index.html", error="Failed to start Spotify authentication.")

@spotify_auth.route("/callback")
def spotify_callback():
    """
    Handles Spotify’s redirect, exchanges code for token, logs analytics.
    """
    try:
        # CSRF check
        state  = request.args.get("state")
        stored = session.get("spotify_csrf_token")
        if not state or state != stored:
            return render_template("index.html", error="Invalid state parameter.")
        session.pop("spotify_csrf_token", None)

        code = request.args.get("code")
        if not code:
            return render_template("index.html", error="No authorization code.")

        # PKCE exchange
        auth_manager = create_auth_manager()
        verifier     = session.get("code_verifier")
        if not verifier:
            return render_template("index.html", error="Session expired.")
        auth_manager.code_verifier   = verifier
        auth_manager.code_challenge  = session.get("code_challenge")

        raw_token = auth_manager.get_access_token(code)
        if not raw_token:
            raise ValueError("Invalid token response.")

        token_info = (
            {"access_token": raw_token}
            if isinstance(raw_token, str)
            else raw_token
        )
        session["token_info"] = token_info
        session["authorized"] = True

        device   = detect_device()
        entry_id = store_login_data(
            ip_address    = request.remote_addr,
            outcome       = "success",
            error_message = None,
            device_type   = device
        )
        session["entry_id"] = entry_id

        return redirect(url_for("home"))

    except Exception as e:
        print(f"Callback Error: {e}")
        store_login_data(
            ip_address    = request.remote_addr,
            outcome       = "failure",
            error_message = str(e),
            device_type   = detect_device()
        )
        return render_template("index.html", error=f"Authentication failed: {e}")

@spotify_auth.route("/logout")
def logout():
    """
    Clears the session and logs the user out.
    """
    for key in ["token_info", "authorized", "entry_id", "code_verifier", "code_challenge"]:
        session.pop(key, None)
    return redirect(url_for("home"))
