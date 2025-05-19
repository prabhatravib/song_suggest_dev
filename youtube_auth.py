import os
from flask import Blueprint, session, redirect, request, url_for, current_app, render_template, flash
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
            flash("YouTube API credentials not configured.", "danger")
            return redirect(url_for('home'))
            
        # Generate state for CSRF protection
        state = secrets.token_hex(16)
        session['youtube_oauth_state'] = state
        session.modified = True  # Force session to be saved
        
        # Store client credentials in session for the callback
        session['youtube_client_id'] = client_id
        session['youtube_client_secret'] = client_secret
        
        # Build the authorization URL
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
        flash(f"YouTube authentication error: {str(e)}", "danger")
        return redirect(url_for('home'))

@youtube_auth.route('/callback')
def callback():
    try:
        # Always check for error parameter
        error = request.args.get('error')
        if error:
            current_app.logger.error(f"YouTube auth error: {error}")
            flash(f"YouTube authentication error: {error}", "danger")
            return redirect(url_for('home'))

        # Get state from query parameters
        state_param = request.args.get('state')
        stored_state = session.get('youtube_oauth_state')
        
        # Debug logging
        current_app.logger.info(f"State from request: {state_param}")
        current_app.logger.info(f"State from session: {stored_state}")
        
        # Verify state parameter
        if not state_param or not stored_state or state_param != stored_state:
            current_app.logger.error(f"State mismatch or missing. Request: {state_param}, Session: {stored_state}")
            flash("Invalid state parameter. Authentication session may have expired.", "danger")
            return redirect(url_for('home'))

        # Get authorization code
        code = request.args.get('code')
        if not code:
            flash("No authorization code received", "danger")
            return redirect(url_for('home'))
        
        # Get client credentials
        client_id = session.get('youtube_client_id') or os.environ.get('YOUTUBE_CLIENT_ID')
        client_secret = session.get('youtube_client_secret') or os.environ.get('YOUTUBE_CLIENT_SECRET')
        
        if not client_id or not client_secret:
            flash("Missing client credentials", "danger")
            return redirect(url_for('home'))
        
        # Exchange code for token
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
            flash(f"Token exchange failed", "danger")
            return redirect(url_for('home'))
        
        token_json = token_response.json()
        
        # Create credentials object
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
        session.modified = True  # Force session to be saved

        # Analytics hook
        from analytics import store_login_data
        try:
            store_login_data(service='youtube', token=session['youtube_credentials'])
            session['entry_id'] = 'youtube-' + secrets.token_hex(8)
            session.modified = True  # Force session to be saved again
        except Exception as analytics_error:
            current_app.logger.error(f"Analytics error: {analytics_error}")

        # Clean up session
        for key in ['youtube_client_id', 'youtube_client_secret', 'youtube_oauth_state']:
            if key in session:
                session.pop(key, None)
        
        flash("YouTube authentication successful!", "success")
        return redirect(url_for('home'))
        
    except Exception as e:
        current_app.logger.error(f"Callback error: {str(e)}")
        flash(f"Authentication error: {str(e)}", "danger")
        return redirect(url_for('home'))
