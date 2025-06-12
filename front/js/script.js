// DOM Elements
const recordBtn = document.getElementById('record-btn');
const statusText = document.getElementById('status-text');
const pulseIndicator = document.querySelector('.pulse');
const targetLanguageSelect = document.getElementById('target-language');
const originalText = document.getElementById('original-text');
const translatedText = document.getElementById('translated-text');
const detectedLanguage = document.getElementById('detected-language');
const translationAudio = document.getElementById('translation-audio');

// State management
let isRecording = false;
let isProcessing = false;

// Language names mapping
const languageNames = {
    'hi': 'Hindi',
    'mr': 'Marathi', 
    'ta': 'Tamil',
    'te': 'Telugu',
    'kn': 'Kannada',
    'gu': 'Gujarati',
    'en': 'English',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'it': 'Italian',
    'pt': 'Portuguese',
    'ru': 'Russian',
    'ja': 'Japanese',
    'ko': 'Korean',
    'zh': 'Chinese',
    'ar': 'Arabic'
};

// Update status function
function updateStatus(message, type = 'default') {
    statusText.textContent = message;
    
    // Reset pulse classes
    pulseIndicator.classList.remove('recording', 'processing');
    
    // Add appropriate class based on type
    switch(type) {
        case 'recording':
            pulseIndicator.classList.add('recording');
            break;
        case 'processing':
            pulseIndicator.classList.add('processing');
            break;
        case 'ready':
        default:
            // Default green state
            break;
    }
}

// Update button state
function updateButtonState(state) {
    recordBtn.classList.remove('recording');
    
    switch(state) {
        case 'recording':
            recordBtn.textContent = '🔴 Recording... (5s)';
            recordBtn.classList.add('recording');
            recordBtn.disabled = true;
            break;
        case 'processing':
            recordBtn.innerHTML = '<span class="loading"></span>Processing...';
            recordBtn.disabled = true;
            break;
        case 'ready':
        default:
            recordBtn.textContent = 'Start Recording';
            recordBtn.disabled = false;
            break;
    }
}

// Clear results
function clearResults() {
    originalText.textContent = '--';
    translatedText.textContent = '--';
    detectedLanguage.textContent = '';
    translationAudio.style.display = 'none';
    translationAudio.src = '';
}

// Display results
function displayResults(data) {
    originalText.textContent = data.original_text || 'No text detected';
    translatedText.textContent = data.translated_text || 'Translation failed';
    
    // Show detected language
    if (data.detected_language) {
        const langName = languageNames[data.detected_language] || data.detected_language;
        detectedLanguage.textContent = `Detected: ${langName}`;
    }
    
    // Handle audio output
    if (data.audio_output) {
        // Note: You'll need to implement proper audio serving from your backend
        // This is a placeholder for the audio handling
        translationAudio.src = data.audio_output;
        translationAudio.style.display = 'block';
    }
}

// Show error message
function showError(message) {
    originalText.textContent = 'Error occurred';
    translatedText.textContent = message;
    detectedLanguage.textContent = '';
    
    // Add error styling temporarily
    const resultBoxes = document.querySelectorAll('.result-box');
    resultBoxes.forEach(box => {
        box.style.backgroundColor = '#f8d7da';
        box.style.borderColor = '#f5c6cb';
        setTimeout(() => {
            box.style.backgroundColor = '#f8f9fa';
            box.style.borderColor = '#e9ecef';
        }, 3000);
    });
}

// Main recording and translation function
async function startRecordingAndTranslation() {
    if (isRecording || isProcessing) return;
    
    try {
        // Clear previous results
        clearResults();
        
        // Start recording phase
        isRecording = true;
        updateStatus('🎤 Recording for 5 seconds...', 'recording');
        updateButtonState('recording');
        
        // Simulate 5-second recording period
        await new Promise(resolve => setTimeout(resolve, 5000));
        
        // Processing phase
        isRecording = false;
        isProcessing = true;
        updateStatus('🔄 Processing your speech...', 'processing');
        updateButtonState('processing');
        
        // Get selected target language
        const targetLang = targetLanguageSelect.value;
        
        // Prepare form data
        const formData = new FormData();
        formData.append('target_lang', targetLang);
        
        // Make API call to backend
        const response = await fetch('/translate', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // Success - display results
            updateStatus('✅ Translation completed successfully!', 'ready');
            displayResults(data);
        } else {
            // API returned error
            throw new Error(data.message || 'Translation failed');
        }
        
    } catch (error) {
        console.error('Translation error:', error);
        updateStatus('❌ Translation failed', 'ready');
        showError(error.message || 'Network error occurred');
    } finally {
        // Reset states
        isRecording = false;
        isProcessing = false;
        updateButtonState('ready');
        
        // Reset to ready status after a delay if successful
        setTimeout(() => {
            if (statusText.textContent.includes('✅')) {
                updateStatus('Ready to record', 'ready');
            }
        }, 3000);
    }
}

// Event listeners
recordBtn.addEventListener('click', startRecordingAndTranslation);

// Language selector change handler
targetLanguageSelect.addEventListener('change', () => {
    if (!isRecording && !isProcessing) {
        const selectedLang = languageNames[targetLanguageSelect.value];
        updateStatus(`Ready to translate to ${selectedLang}`, 'ready');
    }
});

// Keyboard shortcuts
document.addEventListener('keydown', (event) => {
    // Space bar to start recording
    if (event.code === 'Space' && !isRecording && !isProcessing) {
        event.preventDefault();
        startRecordingAndTranslation();
    }
});

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    updateStatus('Ready to record', 'ready');
    updateButtonState('ready');
    
    // Set initial language status
    const selectedLang = languageNames[targetLanguageSelect.value];
    setTimeout(() => {
        updateStatus(`Ready to translate to ${selectedLang}`, 'ready');
    }, 1000);
});

// Handle page visibility change (pause/resume functionality)
document.addEventListener('visibilitychange', () => {
    if (document.hidden && (isRecording || isProcessing)) {
        // Handle tab switching during recording/processing
        console.log('Tab switched during operation');
    }
});

// Error handling for audio playback
translationAudio.addEventListener('error', (e) => {
    console.error('Audio playback error:', e);
    translationAudio.style.display = 'none';
});

// Audio loaded successfully
translationAudio.addEventListener('loadeddata', () => {
    console.log('Audio loaded successfully');
});