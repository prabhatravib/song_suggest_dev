from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from flask_session import Session
import os
import secrets
import html
import re

# Blueprint imports for OAuth flows
from spotify_auth import spotify_auth
from youtube_auth import youtube_auth

# Service client factories
from spotify_service import create_spotify_client
from youtube_service import create_youtube_client

# Recommendation logic
from recommendation_service import process_playlist_and_recommend_song

# Analytics
from analytics import init_analytics_db, store_login_data, update_recommendation_data

app = Flask(__name__)
# Backfill the legacy session_cookie_name property so Flask-Session works on Flask 2.3+
app.session_cookie_name = app.config.get('SESSION_COOKIE_NAME', 'session')

# Secret and session config
decimal_key = os.environ.get("SECRET_KEY") or secrets.token_hex(24)
app.secret_key = decimal_key
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

if os.environ.get('FLASK_ENV') != 'development':
    app.config["SESSION_COOKIE_SECURE"] = True
else:
    app.config["SESSION_COOKIE_SECURE"] = False

app.config["PERMANENT_SESSION_LIFETIME"] = 3600
Session(app)
# Register OAuth blueprints
app.register_blueprint(spotify_auth, url_prefix='/auth/spotify')
app.register_blueprint(youtube_auth, url_prefix='/auth/youtube')

# Initialize analytics database
try:
    init_analytics_db()
except Exception as e:
    app.logger.error(f"Analytics DB init error: {e}")

# Security headers
def add_security_headers(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; frame-ancestors 'none'"
    )
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

app.after_request(add_security_headers)

@app.route('/')
def home():
    return render_template(
        'index.html',
        spotify_authorized=session.get('authorized_spotify', False),
        youtube_authorized=session.get('authorized_youtube', False)
    )

@app.route('/api/playlists')
def api_playlists():
    service = request.args.get('service')
    if service == 'spotify':
        if not session.get('authorized_spotify'):
            return jsonify({'error': 'Authorize Spotify first.'}), 401
        client = create_spotify_client()
        playlists = client.get_user_playlists() if client else []
    elif service == 'youtube':
        if not session.get('authorized_youtube'):
            return jsonify({'error': 'Authorize YouTube first.'}), 401
        client = create_youtube_client()
        playlists = client.get_user_playlists() if client else []
    else:
        return jsonify({'error': 'Unknown service.'}), 400
    return jsonify({'playlists': playlists})

@app.route('/api/recommendation', methods=['POST'])
def api_recommendation():
    try:
        service = request.form.get('service')
        playlist_id = request.form.get('playlist_id')
        language = request.form.get('language', 'english').lower()

        # Validate service selection
        if service not in ['spotify', 'youtube']:
            return jsonify({'error': 'Invalid service.'}), 400

        # Create appropriate client
        if service == 'spotify':
            client = create_spotify_client()
            auth_flag = session.get('authorized_spotify', False)
        else:
            client = create_youtube_client()
            auth_flag = session.get('authorized_youtube', False)

        if not auth_flag or not client:
            return jsonify({'error': f'You must authorize {service.title()} first.'}), 401

        # Run recommendation logic
        result = process_playlist_and_recommend_song(
            service=service,
            playlist_id=playlist_id,  # The extraction happens in the YouTube service
            client=client,
            language=language
        )

        if not result or not result.get('recommendation'):
            return jsonify({'error': 'No recommendation returned.'}), 500

        # Sanitize output
        recommendation = html.escape(result['recommendation'])

        update_recommendation_data(
            session.get('entry_id'),
            service=service,
            playlist_id=playlist_id,
            language=language,
            recommendation=recommendation,
            outcome='success'
        )

        return jsonify({
            'recommendation': recommendation,
            'details': result.get('details', {})
        })

    except Exception as e:
        app.logger.error(f"Recommendation error: {e}", exc_info=True)
        update_recommendation_data(
            session.get('entry_id'),
            service=service,
            playlist_id=playlist_id,
            language=language,
            outcome='failure',
            error_message=str(e)
        )
        return jsonify({'error': 'Unexpected error occurred.'}), 500
        
if __name__ == '__main__':
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(debug=debug)
