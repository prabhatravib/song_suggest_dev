import os
from flask import session
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def create_youtube_client():
    """
    Instantiate and return a YouTube Data API client using stored session credentials.
    Returns None if no valid credentials are present.
    """
    cred_info = session.get('youtube_credentials')
    if not cred_info:
        return None
    creds = Credentials(
        token=cred_info['token'],
        refresh_token=cred_info.get('refresh_token'),
        token_uri=cred_info['token_uri'],
        client_id=cred_info['client_id'],
        client_secret=cred_info['client_secret'],
        scopes=cred_info['scopes']
    )
    return build('youtube', 'v3', credentials=creds)


class YouTubeService:
    def __init__(self, client):
        self.client = client

    def get_user_playlists(self):
        """
        Fetch all of the current user's playlists (id and title).
        """
        playlists = []
        request = self.client.playlists().list(
            part='snippet', mine=True, maxResults=50
        )
        while request:
            response = request.execute()
            for item in response.get('items', []):
                playlists.append({'id': item['id'], 'name': item['snippet']['title']})
            request = self.client.playlists().list_next(request, response)
        return playlists

    def get_playlist_items(self, playlist_id: str):
        """
        Fetch all videos in a given YouTube playlist (id, title, channel).
        """
        items = []
        request = self.client.playlistItems().list(
            part='snippet', playlistId=playlist_id, maxResults=50
        )
        while request:
            response = request.execute()
            for item in response.get('items', []):
                snippet = item['snippet']
                items.append({
                    'id': snippet['resourceId']['videoId'],
                    'name': snippet['title'],
                    'channel': snippet['channelTitle']
                })
            request = self.client.playlistItems().list_next(request, response)
        return items
