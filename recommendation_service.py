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


def _transform_description_regex(description: str) -> str:
    """
    Filter a YouTube description using regex patterns as a fallback method.
    """
    if not description or not description.strip():
        return ""
    
    # Remove URLs
    cleaned = re.sub(r'https?://\S+', '', description)
    
    # Remove common social media patterns
    cleaned = re.sub(r'(?i)follow (me|us) on (twitter|facebook|instagram|tiktok|youtube).*?[\n\r]', '', cleaned)
    cleaned = re.sub(r'(?i)(twitter|facebook|instagram|tiktok):\s*@[\w\._]+', '', cleaned)
    
    # Remove subscription requests
    cleaned = re.sub(r'(?i)(subscribe|like|comment|share|hit the bell).*?[\n\r]', '', cleaned)
    
    # Remove timestamps (e.g., 0:00, 1:23, 01:45)
    cleaned = re.sub(r'\d+:\d+(\:\d+)?(\s+[-–—]\s+.*?)?[\n\r]', '', cleaned)
    
    # Remove copyright notices
    cleaned = re.sub(r'(?i)©.*?(\d{4}).*?[\n\r]', '', cleaned)
    
    # Remove common promotional phrases
    cleaned = re.sub(r'(?i)(available now|buy now|stream on|check out|official video|official audio).*?[\n\r]', '', cleaned)
    
    # Handle multiple consecutive line breaks
    cleaned = re.sub(r'[\n\r]{3,}', '\n\n', cleaned)
    
    # Trim and return
    return cleaned.strip()


def _batch_transform_descriptions(descriptions: List[str], batch_size: int = 50) -> List[str]:
    """
    Transform multiple YouTube descriptions in batches using the OpenAI API.
    
    Args:
        descriptions: List of YouTube descriptions to clean
        batch_size: Number of descriptions to process in a single API call
        
    Returns:
        List of cleaned descriptions in the same order
    """
    if not descriptions:
        return []
    
    _log(f"Batch transforming {len(descriptions)} descriptions")
    cleaned_descriptions = []
    
    # Process descriptions in batches
    for i in range(0, len(descriptions), batch_size):
        batch = descriptions[i:i+batch_size]
        
        # Skip empty descriptions
        batch = [desc if desc and desc.strip() else "" for desc in batch]
        non_empty_indices = [idx for idx, desc in enumerate(batch) if desc]
        
        if not non_empty_indices:
            cleaned_descriptions.extend([""] * len(batch))
            continue
            
        # Limit description length to save tokens
        batch = [desc[:500] if len(desc) > 500 else desc for desc in batch if desc]
        
        # Create a combined prompt
        prompt = f"""
        For each YouTube video description below, remove ONLY the following elements:
        - URLs and links
        - Social media mentions
        - Subscription/like/comment requests
        - Timestamps (0:00, 1:23, etc.)
        - Copyright notices
        - Marketing language
        - Merch promotions
        
        Return ONLY cleaned descriptions, with one description per line, separated by the marker [DESC_END].
        Preserve all other content exactly as is.
        
        DESCRIPTIONS:
        """ + "\n[DESC_START]\n".join(batch) + "\n[DESC_END]"
        
        try:
            _log(f"Sending batch of {len(batch)} descriptions to OpenAI")
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo-16k",  # Using 16k model for larger batches
                messages=[
                    {"role": "system", "content": "You clean YouTube descriptions by removing specified elements."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            result = response.choices[0].message.content.strip()
            
            # Split the results back into individual descriptions
            cleaned_batch = result.split("[DESC_END]")
            cleaned_batch = [desc.strip() for desc in cleaned_batch if desc.strip()]
            
            # Reintegrate with empty descriptions
            full_cleaned_batch = [""] * len(batch)
            for idx, clean_desc in zip(non_empty_indices, cleaned_batch):
                full_cleaned_batch[idx] = clean_desc
                
            cleaned_descriptions.extend(full_cleaned_batch)
            _log(f"Successfully cleaned batch of {len(batch)} descriptions")
            
        except Exception as e:
            _log(f"Error in batch transformation: {e}, falling back to regex cleaning")
            # Fall back to regex-based cleaning if API fails
            cleaned_batch = []
            for desc in batch:
                if not desc:
                    cleaned_batch.append("")
                    continue
                cleaned_batch.append(_transform_description_regex(desc))
                
            cleaned_descriptions.extend(cleaned_batch)
            
    return cleaned_descriptions


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
    """Retrieve YouTube playlist items with enhanced metadata as a DataFrame."""
    svc = YouTubeService(client)
    videos = svc.get_playlist_items(playlist_id)
    if not videos:
        return pd.DataFrame()

    # Collect all descriptions for batch processing
    _log(f"Retrieved {len(videos)} videos from playlist")
    all_descriptions = [video.get('description', '') for video in videos]
    
    # Transform descriptions in batches
    _log(f"Processing {len(all_descriptions)} video descriptions in batches")
    transformed_descriptions = _batch_transform_descriptions(all_descriptions)
    
    # Process videos to add transformed descriptions
    enhanced_videos = []
    for i, video in enumerate(videos):
        enhanced_video = {
            "id": video["id"],
            "name": video["name"],
            "artist": video.get("channel", ""),
            "album": "",
            "published_at": video.get("published_at", ""),
            "description": video.get("description", ""),
            "transformed_description": transformed_descriptions[i] if i < len(transformed_descriptions) else "",
            "tags": video.get("tags", []),
            "topic_categories": video.get("topic_categories", [])
        }
        enhanced_videos.append(enhanced_video)
    
    return pd.DataFrame(enhanced_videos)


def _construct_prompt(df: pd.DataFrame, language: str) -> Tuple[str, List[str]]:
    """Build LLM prompt lines and exclusion list from sample songs."""
    sample_size = min(len(df), 200)
    sample = df.sample(sample_size, random_state=42)

    lines, exclusions = [], []
    for _, row in sample.iterrows():
        # Basic track info
        track_info = f"'{row['name']}' by {row['artist']}"
        
        # Add additional context based on available fields
        extra_info = []
        
        # Add album if available (mainly for Spotify)
        if 'album' in row and row['album']:
            extra_info.append(f"Album: {row['album']}")
            
        # Add tags if available (mainly for YouTube)
        if 'tags' in row and isinstance(row['tags'], list) and row['tags']:
            # Limit to first 5 tags to keep prompt reasonable
            tag_str = ', '.join(row['tags'][:5])
            extra_info.append(f"Tags: {tag_str}")
            
        # Add topic categories if available (YouTube)
        if 'topic_categories' in row and isinstance(row['topic_categories'], list) and row['topic_categories']:
            topic_str = ', '.join(row['topic_categories'][:3])
            extra_info.append(f"Topics: {topic_str}")
            
        # Add publication date if available (YouTube)
        if 'published_at' in row and row['published_at']:
            pub_date = row['published_at'].split('T')[0] if 'T' in row['published_at'] else row['published_at']
            extra_info.append(f"Published: {pub_date}")
            
        # Add transformed description if available and not empty (YouTube)
        if 'transformed_description' in row and row['transformed_description'] and row['transformed_description'] != "No relevant information.":
            desc = row['transformed_description']
            # Keep description brief in the prompt
            if len(desc) > 100:
                desc = desc[:97] + "..."
            extra_info.append(f"Context: {desc}")
            
        # Add audio features if available (Spotify)
        feats = []
        for col in ["danceability", "energy", "tempo", "valence"]:
            if col in row and not pd.isna(row[col]):
                val = float(row[col])
                feats.append(f"{col}={val:.2f}" if col != "tempo" else f"tempo={val:.1f}")
        if feats:
            extra_info.append(f"Features: {', '.join(feats)}")
            
        # Combine all information
        if extra_info:
            lines.append(f"- {track_info} [{' | '.join(extra_info)}]")
        else:
            lines.append(f"- {track_info}")
            
        # Add to exclusion list
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
            language=language
        )
    except Exception as analytics_exc:
        _log(f"Analytics error: {analytics_exc}")

    return {"recommendation": html.escape(recommendation), "details": details}
