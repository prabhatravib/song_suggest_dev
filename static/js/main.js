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

  // Handle Spotify playlist submission
  spotifyForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearMessages();
    showSpinner();
    const url = spotifyForm.playlist_url.value;
    try {
      const response = await fetch('/api/recommendation', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: new URLSearchParams({ service: 'spotify', playlist_id: url, language: languageInput.value })
      });
      const data = await response.json();
      if (data.error) throw new Error(data.error);
      showRecommendation(data.recommendation);
    } catch (err) {
      showMessage(err.message, 'danger');
    } finally {
      hideSpinner();
    }
  });

  // Handle YouTube playlist submission
  youtubeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearMessages();
    showSpinner();
    const url = youtubeForm.playlist_url.value;
    try {
      const response = await fetch('/api/recommendation', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: new URLSearchParams({ service: 'youtube', playlist_id: url, language: languageInput.value })
      });
      const data = await response.json();
      if (data.error) throw new Error(data.error);
      showRecommendation(data.recommendation);
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

  function showRecommendation(text) {
    const p = document.createElement('p');
    p.className = 'lead text-center text-white';
    p.textContent = text;
    recommendationResult.appendChild(p);
  }
});
