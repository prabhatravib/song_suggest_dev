import os
import re
from flask import session
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth


def create_spotify_client():
    """
    Instantiate and return a Spotipy client using the stored token.
    Returns None if no valid token is present in session.
    """
    token_info = session.get('spotify_token')
    if not token_info:
        return None
    return Spotify(auth=token_info['access_token'])


def extract_spotify_playlist_id(playlist_url: str) -> str:
    """
    Extract the playlist ID from various Spotify URL formats.
    
    Handles:
    - Web player: open.spotify.com/playlist/PLAYLIST_ID
    - Web player with additional parameters: open.spotify.com/playlist/PLAYLIST_ID?si=...
    - App URI: spotify:playlist:PLAYLIST_ID
    
    Returns the extracted playlist ID or the original string if no ID was found.
    """
    # Extract from web URL format
    web_pattern = r'spotify\.com/playlist/([a-zA-Z0-9]+)'
    web_match = re.search(web_pattern, playlist_url)
    if web_match:
        return web_match.group(1)
    
    # Extract from URI format
    uri_pattern = r'spotify:playlist:([a-zA-Z0-9]+)'
    uri_match = re.search(uri_pattern, playlist_url)
    if uri_match:
        return uri_match.group(1)
    
    # Return original value if no patterns match (might already be just the ID)
    return playlist_url


class SpotifyService:
    def __init__(self, client: Spotify):
        self.client = client

    def get_user_playlists(self):
        """
        Fetch all of the current user's playlists (id and name).
        """
        playlists = []
        results = self.client.current_user_playlists(limit=50)
        while results:
            for item in results['items']:
                playlists.append({'id': item['id'], 'name': item['name']})
            if results.get('next'):
                results = self.client.next(results)
            else:
                results = None
        return playlists

    def get_playlist_tracks(self, playlist_id: str):
        """
        Fetch all tracks (id, name, artists) from a given playlist.
        """
        # Extract the playlist ID if a full URL was provided
        playlist_id = extract_spotify_playlist_id(playlist_id)
        
        tracks = []
        results = self.client.playlist_items(
            playlist_id,
            additional_types=['track'],
            fields='items.track.id,items.track.name,items.track.artists(name)',
            limit=100
        )
        while results:
            for item in results['items']:
                t = item['track']
                tracks.append({
                    'id': t['id'],
                    'name': t['name'],
                    'artists': [a['name'] for a in t['artists']]
                })
            if results.get('next'):
                results = self.client.next(results)
            else:
                results = None
        return tracks

    def get_audio_features(self, track_ids: list[str]):
        """
        Batch fetch audio features (tempo, energy, danceability, etc.) for up to 100 tracks at a time.
        """
        features = []
        for i in range(0, len(track_ids), 100):
            batch = track_ids[i:i+100]
            audio_feats = self.client.audio_features(batch)
            features.extend([f for f in audio_feats if f])
        return features
