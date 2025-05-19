import os
from flask import Blueprint, session, redirect, request, url_for, current_app
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import secrets
import urllib.parse

youtube_auth = Blueprint('youtube_auth', __name__)

# YouTube readonly scope
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']

def _credentials_to_dict(creds: Credentials) -> dict:
    return {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }

def _get_client_config():
    """Create client config dictionary from environment variables."""
    client_id = os.environ.get('YOUTUBE_CLIENT_ID')
    client_secret = os.environ.get('YOUTUBE_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        current_app.logger.error("Missing YouTube API credentials in environment variables")
        return None
        
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [url_for('youtube_auth.callback', _external=True)]
        }
    }

@youtube_auth.route('/login')
def login():
    # Get client config from environment variables
    client_config = _get_client_config()
    
    if not client_config:
        return "YouTube API credentials not configured. Please set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET environment variables.", 500
        
    # Create flow from client config
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=url_for('youtube_auth.callback', _external=True)
    )
    
    # Generate a random state for CSRF protection
    state = secrets.token_hex(16)
    session['youtube_oauth_state'] = state

    # Get authorization URL
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=state,
        prompt='consent'  # Force consent screen to ensure refresh token
    )
    return redirect(auth_url)

@youtube_auth.route('/callback')
def callback():
    try:
        error = request.args.get('error')
        if error:
            current_app.logger.error(f"YouTube auth error: {error}")
            return f"Error during YouTube authentication: {error}", 400

        # Verify state parameter to prevent CSRF
        state_param = request.args.get('state')
        stored_state = session.get('youtube_oauth_state')
        if not state_param or state_param != stored_state:
            return "Invalid state parameter. This could be a CSRF attempt.", 400

        # Get client config from environment variables
        client_config = _get_client_config()
        if not client_config:
            return "YouTube API credentials not configured", 500
        
        # Create flow instance
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=url_for('youtube_auth.callback', _external=True)
        )
        
        # Fetch the token using the full callback URL
        # We need to disable scope verification to handle Google adding additional scopes
        flow.oauth2session.verify_token_response = False
        
        # Get the authorization code
        code = request.args.get('code')
        token = flow.oauth2session.fetch_token(
            client_config['web']['token_uri'],
            client_secret=client_config['web']['client_secret'],
            code=code,
            include_client_id=True
        )
        
        # Create credentials from the token
        creds = Credentials(
            token=token['access_token'],
            refresh_token=token.get('refresh_token'),
            token_uri=client_config['web']['token_uri'],
            client_id=client_config['web']['client_id'],
            client_secret=client_config['web']['client_secret'],
            scopes=token.get('scope', '').split()
        )
        
        # Store credentials in session
        session['youtube_credentials'] = _credentials_to_dict(creds)
        session['authorized_youtube'] = True

        # Analytics hook
        from analytics import store_login_data
        store_login_data(service='youtube', token=session['youtube_credentials'])

        return redirect(url_for('home'))
        
    except Exception as e:
        current_app.logger.error(f"Callback error: {str(e)}")
        return f"Authentication error: {str(e)}", 500
