/**
 * config.js — runtime configuration
 * 
 * On Render: this file is replaced by render-config-inject.js (see render.yaml)
 * Locally: defaults to localhost:8000
 * 
 * To use a different backend, change TRAFFICGUARD_API_BASE below or
 * set window.TRAFFICGUARD_API_BASE before this script loads.
 */
window.TRAFFICGUARD_API_BASE = window.TRAFFICGUARD_API_BASE
  || "https://trafficguard-backend.onrender.com";   // ← Render will replace this

// Fallback to localhost when running locally (the Render URL won't respond)
(function() {
  // If we're on localhost, always use local backend
  if (window.location.hostname === 'localhost' ||
      window.location.hostname === '127.0.0.1' ||
      window.location.hostname === '[::1]') {
    window.TRAFFICGUARD_API_BASE = 'http://localhost:8000';
  }
})();
