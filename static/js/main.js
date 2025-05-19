// static/js/main.js

document.addEventListener('DOMContentLoaded', () => {
  const serviceRadios = document.querySelectorAll('input[name="service"]');
  const spotifyFlow = document.getElementById('spotify-flow');
  const youtubeFlow = document.getElementById('youtube-flow');
  const spotifyForm = document.getElementById('spotify-url-form');
  const youtubeForm = document.getElementById('youtube-url-form');
  const getBtn = document.getElementById('getRecommendationBtn');
  const spinner = document.getElementById('recommendationSpinner');
  const messagesArea = document.getElementById('messagesArea');
  const recommendationResult = document.getElementById('recommendationResult');
  const languageInput = document.getElementById('languageInput');

  // Track the current loaded playlist
  let currentPlaylist = {
    service: null,
    playlistId: null,
    isLoaded: false
  };

  // Toggle between Spotify and YouTube flows
  serviceRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      if (radio.value === 'spotify' && radio.checked) {
        spotifyFlow.style.display = '';
        youtubeFlow.style.display = 'none';
      } else if (radio.value === 'youtube' && radio.checked) {
        spotifyFlow.style.display = 'none';
        youtubeFlow.style.display = '';
      }
    });
  });

  // Handle Spotify playlist submission - just validate and load the playlist
  spotifyForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearMessages();
    showSpinner();
    const url = spotifyForm.playlist_url.value;
    
    try {
      // Just store the playlist info for now
      currentPlaylist = {
        service: 'spotify',
        playlistId: url,
        isLoaded: true
      };
      
      // Show success message
      showMessage('Playlist loaded successfully!', 'success');
      
      // Display the loaded playlist info
      const playlistInfo = document.createElement('p');
      playlistInfo.className = 'text-light mb-3';
      playlistInfo.innerHTML = `<strong>Loaded Playlist:</strong> ${url}`;
      playlistInfo.id = 'loadedPlaylistInfo';
      
      // Remove any existing playlist info before adding new one
      const existingInfo = document.getElementById('loadedPlaylistInfo');
      if (existingInfo) existingInfo.remove();
      
      const languageSection = document.querySelector('#languageInput').closest('div').closest('div');
      languageSection.insertAdjacentElement('beforebegin', playlistInfo);
    } catch (err) {
      showMessage(err.message, 'danger');
      currentPlaylist.isLoaded = false;
    } finally {
      hideSpinner();
    }
  });

  // Handle YouTube playlist submission - just validate and load the playlist
  youtubeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearMessages();
    showSpinner();
    const url = youtubeForm.playlist_url.value;
    
    try {
      // Just store the playlist info for now
      currentPlaylist = {
        service: 'youtube',
        playlistId: url,
        isLoaded: true
      };
      
      // Show success message
      showMessage('Playlist loaded successfully!', 'success');
      
      // Display the loaded playlist info
      const playlistInfo = document.createElement('p');
      playlistInfo.className = 'text-light mb-3';
      playlistInfo.innerHTML = `<strong>Loaded Playlist:</strong> ${url}`;
      playlistInfo.id = 'loadedPlaylistInfo';
      
      // Remove any existing playlist info before adding new one
      const existingInfo = document.getElementById('loadedPlaylistInfo');
      if (existingInfo) existingInfo.remove();
      
      const languageSection = document.querySelector('#languageInput').closest('div').closest('div');
      languageSection.insertAdjacentElement('beforebegin', playlistInfo);
    } catch (err) {
      showMessage(err.message, 'danger');
      currentPlaylist.isLoaded = false;
    } finally {
      hideSpinner();
    }
  });

  // Handle Get Suggestion button click - now this makes the recommendation API call
  getBtn.addEventListener('click', async () => {
    if (!currentPlaylist.isLoaded) {
      showMessage('Please load a playlist first.', 'warning');
      return;
    }
    
    clearMessages();
    showSpinner();
    
    try {
      const response = await fetch('/api/recommendation', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: new URLSearchParams({ 
          service: currentPlaylist.service, 
          playlist_id: currentPlaylist.playlistId, 
          language: languageInput.value 
        })
      });
      
      const data = await response.json();
      if (data.error) throw new Error(data.error);
      showRecommendation(data.recommendation, data.details);
    } catch (err) {
      showMessage(err.message, 'danger');
    } finally {
      hideSpinner();
    }
  });

  function showSpinner() {
    spinner.style.display = '';
    getBtn.disabled = true;
  }

  function hideSpinner() {
    spinner.style.display = 'none';
    getBtn.disabled = false;
  }

  function showMessage(message, type = 'info') {
    const div = document.createElement('div');
    div.className = `alert alert-${type}`;
    div.textContent = message;
    messagesArea.appendChild(div);
  }

  function clearMessages() {
    messagesArea.innerHTML = '';
    recommendationResult.innerHTML = '';
  }

  function showRecommendation(text, details) {
    const container = document.createElement('div');
    container.className = 'recommendation-card bg-dark text-white p-4 rounded text-center mb-4';
    
    // Add header
    const header = document.createElement('p');
    header.className = 'mb-3';
    header.textContent = 'Suggested song is:';
    container.appendChild(header);
    
    // Add song title in larger text
    const title = document.createElement('h4');
    title.className = 'mb-4';
    // Decode HTML entities
    const decodedText = decodeHTMLEntities(text);
    title.textContent = decodedText;
    container.appendChild(title);
    
    // Add YouTube button if we have details
    if (details && details.youtube && details.youtube.url) {
      const button = document.createElement('a');
      button.href = details.youtube.url;
      button.className = 'btn btn-danger';
      button.textContent = 'Play on YouTube';
      button.target = '_blank';
      button.rel = 'noopener noreferrer';
      container.appendChild(button);
    }
    
    recommendationResult.appendChild(container);
  }

  // Helper function to decode HTML entities
  function decodeHTMLEntities(text) {
    // First, use the browser's built-in decoder
    const textArea = document.createElement('textarea');
    textArea.innerHTML = text;
    let decoded = textArea.value;
    
    // Then handle any remaining entities that might not be properly decoded
    decoded = decoded.replace(/&quot;/g, '"');
    decoded = decoded.replace(/&#39;/g, "'");
    decoded = decoded.replace(/&amp;/g, '&');
    decoded = decoded.replace(/&lt;/g, '<');
    decoded = decoded.replace(/&gt;/g, '>');
    
    return decoded;
  }
});
