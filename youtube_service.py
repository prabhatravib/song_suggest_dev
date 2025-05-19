import os
import re
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


def extract_youtube_playlist_id(url: str) -> str:
    """
    Extract the playlist ID from various YouTube URL formats.
    
    Handles:
    - Standard YouTube: youtube.com/playlist?list=PLAYLIST_ID
    - YouTube Music: music.youtube.com/playlist?list=PLAYLIST_ID
    - YouTube Shortlink: youtu.be/VIDEO_ID?list=PLAYLIST_ID
    - YouTube embedded: youtube.com/embed/VIDEO_ID?list=PLAYLIST_ID
    - YouTube watch: youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ID
    """
    import re
    
    # Try to extract the playlist ID using regex - match more specifically
    playlist_pattern = r'[?&]list=([a-zA-Z0-9_-]+)'
    match = re.search(playlist_pattern, url)
    
    if match:
        return match.group(1)  # Return just the ID portion
        
    # Try alternative patterns for different URL formats
    alternate_pattern = r'youtube\.com/playlist/([a-zA-Z0-9_-]+)'
    alt_match = re.search(alternate_pattern, url)
    if alt_match:
        return alt_match.group(1)
    
    # If no match found and it looks like a URL, log a warning
    if '/' in url or '?' in url:
        print(f"Warning: Could not extract playlist ID from: {url}")
        
    # Return the original value (it might already be just the ID)
    return url


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
        Fetch all videos in a given YouTube playlist with enhanced metadata:
        - Basic info (id, title/name, channel)
        - Publication date
        - Description
        - Tags/keywords
        - Topic categories
        """
        # Extract the playlist ID if a full URL was provided
        playlist_id = extract_youtube_playlist_id(playlist_id)
        
        items = []
        # First, get all playlist items
        request = self.client.playlistItems().list(
            part='snippet,contentDetails',
            playlistId=playlist_id,
            maxResults=50
        )
        
        while request:
            response = request.execute()
            video_ids = []
            temp_items = {}
            
            # Process basic playlist item info
            for item in response.get('items', []):
                snippet = item['snippet']
                video_id = snippet['resourceId']['videoId']
                video_ids.append(video_id)
                
                # Store basic info in temporary dictionary
                temp_items[video_id] = {
                    'id': video_id,
                    'name': snippet['title'],
                    'channel': snippet['channelTitle'],
                    'published_at': snippet['publishedAt'],
                    'description': snippet['description'],
                    'album': ''  # YouTube videos don't have album info
                }
            
            # Batch request additional video details in chunks of 50
            for i in range(0, len(video_ids), 50):
                chunk = video_ids[i:i+50]
                video_response = self.client.videos().list(
                    part='snippet,topicDetails',
                    id=','.join(chunk)
                ).execute()
                
                # Process additional video details
                for video in video_response.get('items', []):
                    video_id = video['id']
                    if video_id in temp_items:
                        # Add tags
                        temp_items[video_id]['tags'] = video['snippet'].get('tags', [])
                        
                        # Add topic categories if available
                        if 'topicDetails' in video:
                            topic_categories = video['topicDetails'].get('relevantTopicIds', [])
                            temp_items[video_id]['topic_categories'] = topic_categories
                        else:
                            temp_items[video_id]['topic_categories'] = []
            
            # Add all processed items to the result list
            items.extend(temp_items.values())
            
            # Get next page of results if available
            request = self.client.playlistItems().list_next(request, response)
            
        return items
