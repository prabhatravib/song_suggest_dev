# SongSuggest Dev

A Flask-based web application that recommends songs using Spotify and YouTube playlists combined with OpenAI’s LLMs.

## Features

* **Multi-Service Support**: Accepts Spotify and YouTube playlist URLs.
* **Sophisticated Recommendation Pipeline**:

  * Fetches audio features (Spotify) or metadata (YouTube).
  * Constructs detailed prompts with sampled tracks and musical attributes.
  * Queries multiple OpenAI models with duplicate filtering and cost estimation.
  * Provides direct YouTube links for recommended songs.
* **Analytics**: Logs login events and recommendation outcomes in SQLite.

## Repository Structure

```
song_suggest_dev/
├── app.py                  # Flask application entry point
├── spotify_auth.py         # Spotify OAuth PKCE flow
├── spotify_service.py      # Spotify API wrapper
├── youtube_auth.py         # YouTube OAuth flow
├── youtube_service.py      # YouTube API wrapper
├── recommendation_service.py  # Core recommendation logic
├── analytics.py            # SQLite analytics hooks
├── requirements.txt        # Python dependencies
├── Procfile                # Gunicorn process definition
├── .gitignore
├── README.md
├── templates/
│   └── index.html          # Main UI, dynamic recommendation
└── static/
    ├── css/main.css        # Styles
    ├── js/main.js          # Frontend logic
    └── images/             # background.png, favicon.png
```

## Setup & Installation

1. **Clone the repo**

   ```bash
   git clone https://github.com/prabhatravib/song_suggest_dev.git
   cd song_suggest_dev
   ```

2. **Create & activate a virtual environment**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**

   ```bash
   export FLASK_ENV=development
   export SPOTIFY_CLIENT_ID=<your_spotify_client_id>
   export SPOTIFY_CLIENT_SECRET=<your_spotify_client_secret>
   export GOOGLE_CLIENT_SECRETS_FILE=<path_to_client_secrets.json>
   export OPENAI_API_KEY=<your_openai_api_key>
   export YOUTUBE_API_KEY=<your_youtube_api_key>
   ```

5. **Initialize analytics database**

   ```bash
   python -c "from analytics import init_analytics_db; init_analytics_db()"
   ```

6. **Run the application**

   ```bash
   flask run
   ```

## Deployment

* Uses **Gunicorn** as WSGI server defined in `Procfile`.
* Can deploy to **Render**, **Heroku**, or any platform supporting Gunicorn.

## Usage

1. Visit `http://localhost:5000`
2. Select **Spotify** or **YouTube**, authenticate, and submit a playlist URL.
3. Enter your preferred language and click **Get Suggestion**.
4. View the recommendation dynamically on the same page, including model details and logs.

---

© 2025 SongSuggest Dev Contributors
