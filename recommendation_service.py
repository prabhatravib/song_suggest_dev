"""
recommendation_service.py

Sophisticated music recommendation pipeline supporting Spotify and YouTube playlists.
Includes feature extraction, prompt construction, multi-model querying,
fuzzy duplicate filtering, cost estimation, YouTube link lookup,
and analytics logging.
"""
import os
import re
import html
import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional

import pandas as pd
import openai
import requests
from flask import session, current_app
from googleapiclient.discovery import build
from requests.adapters import HTTPAdapter, Retry
from fuzzywuzzy import fuzz

from spotify_service import SpotifyService
from youtube_service import YouTubeService
from analytics import update_recommendation_data


# ----------------------- Configuration -----------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY") or current_app.config.get("OPENAI_API_KEY")
YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY") or current_app.config.get("YOUTUBE_API_KEY")
if not OPENAI_API_KEY or not YOUTUBE_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY or YOUTUBE_API_KEY configuration.")
openai.api_key = OPENAI_API_KEY

MODELS_TO_TRY: List[str] = [os.getenv("OPENAI_MODEL", "gpt-4"), "gpt-3.5-turbo"]
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4": {"input": 3.0, "output": 12.0},
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
}
MAX_ATTEMPTS: int = 3

# HTTP session with retry strategy
HTTP_SESSION = requests.Session()
HTTP_SESSION.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(total=5, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])
    ),
)

# Logger setup
log = logging.getLogger(__name__)
LOG_BUFFER: List[str] = []


# ------------------------- Helpers ---------------------------
def _log(message: str) -> None:
    """Add timestamped entry to buffer and application log."""
    timestamp = datetime.utcnow().isoformat()
    entry = f"[{timestamp}] {message}"
    LOG_BUFFER.append(entry)
    log.debug(entry)


def _calculate_cost(usage: Dict[str, int], model: str) -> float:
    """Compute approximate cost ($) from token usage."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("gpt-3.5-turbo"))
    cost_in = usage.get("prompt_tokens", 0) / 1e6 * pricing["input"]
    cost_out = usage.get("completion_tokens", 0) / 1e6 * pricing["output"]
    return cost_in + cost_out


def _fetch_spotify_dataframe(playlist_id: str, client: Any) -> pd.DataFrame:
    """Retrieve Spotify tracks and features as a DataFrame."""
    svc = SpotifyService(client)
    tracks = svc.get_playlist_tracks(playlist_id)
    if not tracks:
        return pd.DataFrame()

    df_feats = pd.DataFrame(svc.get_audio_features([t["id"] for t in tracks]))
    df_meta = pd.DataFrame(
        [{"id": t["id"], "name": t["name"], "artist": t["artists"][0] if t["artists"] else "", "album": t.get("album", "")} for t in tracks]
    )
    return df_meta.merge(df_feats, on="id", how="inner")


def _fetch_youtube_dataframe(playlist_id: str, client: Any) -> pd.DataFrame:
    """Retrieve YouTube playlist items as a DataFrame."""
    svc = YouTubeService(client)
    videos = svc.get_playlist_items(playlist_id)
    if not videos:
        return pd.DataFrame()

    return pd.DataFrame(
        [{"id": v["id"], "name": v["name"], "artist": v.get("channel", ""), "album": ""} for v in videos]
    )


def _construct_prompt(df: pd.DataFrame, language: str) -> Tuple[str, List[str]]:
    """Build LLM prompt lines and exclusion list from sample songs."""
    sample_size = min(len(df), 200)
    sample = df.sample(sample_size, random_state=42)

    lines, exclusions = [], []
    for _, row in sample.iterrows():
        feats = []
        for col in ["danceability", "energy", "tempo", "valence"]:
            if col in row:
                val = float(row[col])
                feats.append(f"{col}={val:.2f}" if col != "tempo" else f"tempo={val:.1f}")
        lines.append(f"- '{row['name']}' by {row['artist']} [{', '.join(feats)}]")
        exclusions.append(row['name'].lower())

    prompt = (
        f"You are a music curator. Analyze these songs and recommend one new song not listed, in {html.escape(language)}.\n\n"
        + "\n".join(lines)
        + "\n\nExclude: " + ", ".join(f'"{s}"' for s in exclusions)
        + "\nProvide ONLY: Title - Artist - Album"
    )
    return prompt, exclusions


def _query_model(prompt: str, exclusion: List[str], model: str) -> Tuple[str, Dict[str, Any]]:
    """Attempt multiple times to get a non-duplicate recommendation from given model."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        temp = 0.6 + 0.1 * attempt
        _log(f"Querying {model}, attempt {attempt}, temperature={temp}")
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a refined music recommendation assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=temp,
            max_tokens=150,
        )
        rec = resp.choices[0].message.content.strip()
        title = rec.split(" - ")[0].strip().lower().strip('"')
        clean_title = re.sub(r"[^a-z0-9]", "", title)
        if any(fuzz.ratio(clean_title, re.sub(r"[^a-z0-9]", "", ex)) > 85 for ex in exclusion):
            _log(f"Duplicate detected ({title}), retrying...")
            continue
        usage = {"prompt_tokens": resp.usage.prompt_tokens, "completion_tokens": resp.usage.completion_tokens}
        return rec, {"usage": usage, "model": model}
    raise RuntimeError(f"No unique recommendation after {MAX_ATTEMPTS} attempts with {model}")


def _search_youtube_video(query: str) -> Optional[Dict[str, Any]]:
    """Find top YouTube video matching query."""
    yt = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    resp = yt.search().list(part="snippet", q=query, maxResults=1, type="video").execute()
    items = resp.get("items", [])
    if not items:
        return None
    it = items[0]
    vid = it["id"].get("videoId")
    return {
        "video_id": vid,
        "title": it["snippet"]["title"],
        "channel": it["snippet"]["channelTitle"],
        "url": f"https://youtu.be/{vid}"
    }


# ---------------------- Main Entry Point ---------------------
def process_playlist_and_recommend_song(
    service: str,
    playlist_id: str,
    client: Any,
    language: str = "english",
) -> Dict[str, Any]:
    """
    Core pipeline: fetch data, build prompt, query models, assemble result, send analytics.
    """
    LOG_BUFFER.clear()
    df = (
        _fetch_spotify_dataframe(playlist_id, client)
        if service == "spotify"
        else _fetch_youtube_dataframe(playlist_id, client)
    )
    if df.empty:
        error = "Playlist data unavailable or empty."
        _log(error)
        return {"recommendation": None, "details": {"error": error, "logs": LOG_BUFFER}}

    prompt, exclusions = _construct_prompt(df, language)
    recommendation, details = None, {}

    for model in MODELS_TO_TRY:
        try:
            rec_text, meta = _query_model(prompt, exclusions, model)
            cost = _calculate_cost(meta["usage"], meta["model"])
            _log(f"Success with {meta['model']}, cost=${cost:.6f}")
            yt_info = _search_youtube_video(rec_text)
            details = {"model": meta["model"], "cost_usd": cost, "youtube": yt_info, "logs": LOG_BUFFER.copy()}
            recommendation = rec_text
            break
        except Exception as exc:
            _log(str(exc))

    if not recommendation:
        error = "Failed to generate recommendation with all models."
        _log(error)
        return {"recommendation": None, "details": {"error": error, "logs": LOG_BUFFER}}

    # Record analytics
    try:
        update_recommendation_data(
            session_id=session.get("entry_id"),
            service=service,
            playlist_id=playlist_id,
            recommendation=recommendation,
            details=details,
        )
    except Exception as analytics_exc:
        _log(f"Analytics error: {analytics_exc}")

    return {"recommendation": html.escape(recommendation), "details": details}
