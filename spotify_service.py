import os
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
