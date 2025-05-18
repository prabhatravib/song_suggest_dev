import os
from flask import Blueprint, session, redirect, request, url_for, current_app
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

youtube_auth = Blueprint('youtube_auth', __name__)

# Path to client secrets JSON file
CLIENT_SECRETS_FILE = os.environ.get('GOOGLE_CLIENT_SECRETS_FILE', 'client_secrets.json')
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

@youtube_auth.route('/login')
def login():
    # Create the OAuth flow using client secrets
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('youtube_auth.callback', _external=True)
    )
    # Store the state in session to verify callback
    session['youtube_oauth_state'] = flow.state

    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    return redirect(auth_url)

@youtube_auth.route('/callback')
def callback():
    error = request.args.get('error')
    if error:
        current_app.logger.error(f"YouTube auth error: {error}")
        return f"Error during YouTube authentication: {error}", 400

    # Recreate flow with the state saved
    state = session.get('youtube_oauth_state')
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=url_for('youtube_auth.callback', _external=True)
    )
    # Fetch the token using the full callback URL
    flow.fetch_token(authorization_response=request.url)

    creds = flow.credentials
    # Store credentials in session
    session['youtube_credentials'] = _credentials_to_dict(creds)
    session['authorized_youtube'] = True

    # Analytics hook
    from analytics import store_login_data
    store_login_data(service='youtube', token=session['youtube_credentials'])

    return redirect(url_for('home'))
