import os
from flask import Blueprint, session, redirect, request, url_for, current_app, render_template
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import secrets

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
    try:
        # Get client config from environment variables
        client_config = _get_client_config()
        
        if not client_config:
            return "YouTube API credentials not configured.", 500
            
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
        auth_url = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=state,
            prompt='consent'  # Force consent screen to ensure refresh token
        )[0]  # Only take the URL, ignore the state
        
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

        # Get client config from environment variables
        client_config = _get_client_config()
        if not client_config:
            return render_template("index.html", error="YouTube API credentials not configured")
        
        # Create flow instance
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=url_for('youtube_auth.callback', _external=True)
        )
        
        # Disable scope checking completely
        if hasattr(flow, 'oauth2session'):
            flow.oauth2session.compliance_hook = {'access_token_response': []}
        
        # Exchange code for token
        code = request.args.get('code')
        if not code:
            return render_template("index.html", error="No authorization code received")
            
        flow.fetch_token(code=code)
        
        # Get credentials
        creds = flow.credentials
        
        # Store credentials in session
        session['youtube_credentials'] = _credentials_to_dict(creds)
        session['authorized_youtube'] = True

        # Analytics hook
        from analytics import store_login_data
        store_login_data(service='youtube', token=session['youtube_credentials'])

        return redirect(url_for('home'))
        
    except Exception as e:
        current_app.logger.error(f"Callback error: {str(e)}")
        return render_template("index.html", error=f"Authentication error: {str(e)}")
