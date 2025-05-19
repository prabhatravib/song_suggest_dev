import os
from flask import Blueprint, session, redirect, request, url_for, current_app, render_template
from google.oauth2.credentials import Credentials
import secrets
import json
import requests

youtube_auth = Blueprint('youtube_auth', __name__)

# Include all scopes that Google will add automatically
SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
    'openid',
    'https://www.googleapis.com/auth/userinfo.profile'
]

def _credentials_to_dict(creds: Credentials) -> dict:
    return {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }

@youtube_auth.route('/login')
def login():
    try:
        # Get credentials from environment variables
        client_id = os.environ.get('YOUTUBE_CLIENT_ID')
        client_secret = os.environ.get('YOUTUBE_CLIENT_SECRET')
        
        if not client_id or not client_secret:
            return render_template("index.html", error="YouTube API credentials not configured.")
            
        # Generate state for CSRF protection
        state = secrets.token_hex(16)
        session['youtube_oauth_state'] = state
        
        # Store client credentials in session for the callback
        session['youtube_client_id'] = client_id
        session['youtube_client_secret'] = client_secret
        
        # Build the authorization URL manually
        redirect_uri = url_for('youtube_auth.callback', _external=True)
        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(SCOPES),
            'state': state,
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        # Construct the auth URL
        auth_url = "https://accounts.google.com/o/oauth2/auth?" + "&".join(f"{k}={v}" for k, v in params.items())
        
        return redirect(auth_url)
    except Exception as e:
        current_app.logger.error(f"Login error: {str(e)}")
        return render_template("index.html", error=f"YouTube authentication error: {str(e)}")

@youtube_auth.route('/callback')
def callback():
    try:
        error = request.args.get('error')
        if error:
            current_app.logger.error(f"YouTube auth error: {error}")
            return render_template("index.html", error=f"YouTube authentication error: {error}")

        # Verify state parameter to prevent CSRF
        state_param = request.args.get('state')
        stored_state = session.get('youtube_oauth_state')
        if not state_param or state_param != stored_state:
            return render_template("index.html", error="Invalid state parameter. This could be a CSRF attempt.")

        # Get authorization code
        code = request.args.get('code')
        if not code:
            return render_template("index.html", error="No authorization code received")
        
        # Get credentials from session
        client_id = session.get('youtube_client_id')
        client_secret = session.get('youtube_client_secret')
        
        if not client_id or not client_secret:
            return render_template("index.html", error="Missing client credentials in session")
        
        # Exchange code for token directly using requests
        redirect_uri = url_for('youtube_auth.callback', _external=True)
        token_url = "https://oauth2.googleapis.com/token"
        
        token_data = {
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }
        
        # Make the token request
        token_response = requests.post(token_url, data=token_data)
        
        if token_response.status_code != 200:
            current_app.logger.error(f"Token request failed: {token_response.text}")
            return render_template("index.html", error=f"Token exchange failed: {token_response.text}")
        
        token_json = token_response.json()
        
        # Create credentials from token response
        creds = Credentials(
            token=token_json['access_token'],
            refresh_token=token_json.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=token_json.get('scope', '').split()
        )
        
        # Store credentials in session
        session['youtube_credentials'] = _credentials_to_dict(creds)
        session['authorized_youtube'] = True

        # Analytics hook
        from analytics import store_login_data
        store_login_data(service='youtube', token=session['youtube_credentials'])

        # Clean up session
        session.pop('youtube_client_id', None)
        session.pop('youtube_client_secret', None)
        session.pop('youtube_oauth_state', None)

        return redirect(url_for('home'))
        
    except Exception as e:
        current_app.logger.error(f"Callback error: {str(e)}")
        return render_template("index.html", error=f"Authentication error: {str(e)}")
