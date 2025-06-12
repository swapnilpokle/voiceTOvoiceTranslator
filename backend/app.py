from flask import Flask, request, jsonify, render_template_string
from asr_module import ASRModule
from mt_module import PreloadedTranslator
from tts_module import TTSModule
import os
import tempfile
import threading
import time
import uuid
from collections import deque
import logging

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), 'static'),
    static_url_path='/static'
)

# Initialize modules with error handling
try:
    logger.info("Initializing ASR module...")
    asr = ASRModule()
    logger.info("ASR module initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize ASR module: {e}")
    asr = None

try:
    logger.info("Initializing translator...")
    translator = PreloadedTranslator(gemini_api_key="AIzaSyBVtcSFbdPwT0yL5eSb-XuY-XWUzVmTBO8")
    logger.info("Translator initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize translator: {e}")
    translator = None

try:
    logger.info("Initializing TTS module...")
    tts = TTSModule()
    logger.info("TTS module initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize TTS module: {e}")
    tts = None

# Cache for recent translations to avoid duplicates
translation_cache = deque(maxlen=10)
audio_cache = {}

# Thread pool for async processing
processing_threads = {}

class TranslationProcessor:
    def __init__(self, max_concurrent=3):
        self.max_concurrent = max_concurrent
        self.active_processes = 0
        self.lock = threading.Lock()
    
    def can_process(self):
        with self.lock:
            return self.active_processes < self.max_concurrent
    
    def start_process(self):
        with self.lock:
            self.active_processes += 1
    
    def end_process(self):
        with self.lock:
            self.active_processes = max(0, self.active_processes - 1)

processor = TranslationProcessor()

@app.route('/')
def index():
    # Read the enhanced HTML file
    try:
        with open('templates/index.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        # Fallback to basic template if file doesn't exist
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>TalkLingo - Real-time Translation</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body>
            <h1>TalkLingo - Real-time Translation</h1>
            <p>Please make sure the enhanced HTML template is in the templates folder.</p>
        </body>
        </html>
        """)

def is_similar_text(new_text, threshold=0.8):
    """Check if the new text is too similar to recent translations"""
    new_text_lower = new_text.lower().strip()
    if len(new_text_lower) < 3:  # Skip very short texts
        return True
    
    for cached_text in translation_cache:
        cached_lower = cached_text.lower().strip()
        # Simple similarity check based on common words
        words_new = set(new_text_lower.split())
        words_cached = set(cached_lower.split())
        
        if len(words_new) > 0 and len(words_cached) > 0:
            intersection = len(words_new.intersection(words_cached))
            union = len(words_new.union(words_cached))
            similarity = intersection / union if union > 0 else 0
            
            if similarity > threshold:
                return True
    
    return False

def clean_audio_files():
    """Clean up old audio files to prevent disk space issues"""
    try:
        audio_dir = os.path.join("static", "audio")
        if os.path.exists(audio_dir):
            now = time.time()
            for filename in os.listdir(audio_dir):
                filepath = os.path.join(audio_dir, filename)
                if os.path.isfile(filepath):
                    # Remove files older than 5 minutes
                    if now - os.path.getctime(filepath) > 300:
                        os.remove(filepath)
                        logger.info(f"Cleaned up old audio file: {filename}")
    except Exception as e:
        logger.error(f"Error cleaning audio files: {e}")

@app.route('/translate', methods=['POST'])
def translate():
    start_time = time.time()
    
    # Check if modules are initialized
    if not asr:
        return jsonify({
            'status': 'error',
            'message': 'Speech recognition module not available'
        }), 503
    
    if not translator:
        return jsonify({
            'status': 'error',
            'message': 'Translation module not available'
        }), 503
    
    # Check if we can process this request
    if not processor.can_process():
        return jsonify({
            'status': 'busy', 
            'message': 'Server busy, please try again'
        }), 429
    
    processor.start_process()
    audio_path = None
    
    try:
        # Validate request
        if 'audio_data' not in request.files:
            return jsonify({
                'status': 'error', 
                'message': 'No audio file provided'
            }), 400

        audio_file = request.files['audio_data']
        target_lang = request.form.get('target_lang', 'hi')
        
        logger.info(f"Received translation request for target language: {target_lang}")
        
        # Check file size (limit to 10MB)
        audio_file.seek(0, 2)  # Seek to end
        file_size = audio_file.tell()
        audio_file.seek(0)  # Reset to beginning
        
        logger.info(f"Audio file size: {file_size} bytes")
        
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            return jsonify({
                'status': 'error',
                'message': 'Audio file too large'
            }), 413
        
        if file_size < 500:  # Too small, likely silence
            logger.info("Audio file too small, likely silence")
            return jsonify({
                'status': 'success',
                'original_text': '',
                'detected_language': 'unknown',
                'translated_text': '',
                'audio_output': None,
                'processing_time': time.time() - start_time
            })

        # Save temporary audio file with proper extension
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp:
            audio_path = tmp.name
            audio_file.save(audio_path)

        logger.info(f"Saved audio file to: {audio_path} ({file_size} bytes)")

        # Step 1: Transcribe audio
        transcription_start = time.time()
        try:
            text, detected_lang = asr.transcribe_audio(audio_path)
            logger.info(f"ASR result - Text: '{text}', Language: {detected_lang}")
        except Exception as e:
            logger.error(f"ASR error: {e}")
            return jsonify({
                'status': 'error',
                'message': f'Speech recognition failed: {str(e)}'
            }), 500
        
        transcription_time = time.time() - transcription_start
        logger.info(f"Transcription completed in {transcription_time:.2f}s")

        # Check if text is meaningful
        if not text or len(text.strip()) < 2:
            logger.info("No meaningful text detected")
            return jsonify({
                'status': 'success',
                'original_text': text or '',
                'detected_language': detected_lang or 'unknown',
                'translated_text': '',
                'audio_output': None,
                'processing_time': time.time() - start_time
            })

        # Check for similar recent translations
        if is_similar_text(text):
            logger.info(f"Skipping similar text: '{text}'")
            return jsonify({
                'status': 'success',
                'original_text': text,
                'detected_language': detected_lang,
                'translated_text': '',
                'audio_output': None,
                'processing_time': time.time() - start_time,
                'skipped': True
            })

        # Step 2: Translate text
        translation_start = time.time()
        try:
            translated_text = translator.translate_with_detection(text, target_lang)
            logger.info(f"Translation result: '{translated_text}'")
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return jsonify({
                'status': 'error',
                'message': f'Translation failed: {str(e)}'
            }), 500
        
        translation_time = time.time() - translation_start
        logger.info(f"Translation completed in {translation_time:.2f}s")

        # Skip if translation is same as original (no translation needed)
        if translated_text.lower().strip() == text.lower().strip():
            logger.info("No translation needed - text is already in target language")
            return jsonify({
                'status': 'success',
                'original_text': text,
                'detected_language': detected_lang,
                'translated_text': translated_text,
                'audio_output': None,
                'processing_time': time.time() - start_time,
                'no_translation_needed': True
            })

        # Step 3: Generate speech (if TTS is available)
        audio_output_url = None
        tts_time = 0
        
        if tts and translated_text and len(translated_text.strip()) > 0:
            try:
                # Create unique filename
                audio_filename = f"output_{uuid.uuid4().hex[:8]}_{int(time.time())}.mp3"
                output_dir = os.path.join("static", "audio")
                os.makedirs(output_dir, exist_ok=True)
                output_audio = os.path.join(output_dir, audio_filename)
                
                # Generate TTS
                tts_start = time.time()
                tts.sync_text_to_speech(translated_text, target_lang, output_audio)
                tts_time = time.time() - tts_start
                logger.info(f"TTS completed in {tts_time:.2f}s")
                
                audio_output_url = f'/static/audio/{audio_filename}'
                
                # Cache the audio file info for cleanup
                audio_cache[audio_filename] = time.time()
                
            except Exception as e:
                logger.error(f"TTS error: {e}")
                # Continue without audio if TTS fails
                pass

        # Add to cache to prevent duplicates
        translation_cache.append(text)
        
        # Clean up old files periodically
        if len(audio_cache) > 20:
            threading.Thread(target=clean_audio_files, daemon=True).start()

        total_time = time.time() - start_time
        logger.info(f"Total processing time: {total_time:.2f}s")

        return jsonify({
            'status': 'success',
            'original_text': text,
            'detected_language': detected_lang,
            'translated_text': translated_text,
            'audio_output': audio_output_url,
            'processing_time': total_time,
            'timing': {
                'transcription': transcription_time,
                'translation': translation_time,
                'tts': tts_time
            }
        })

    except Exception as e:
        logger.error(f"Unexpected error in translate endpoint: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': 'An unexpected error occurred'
        }), 500
    
    finally:
        processor.end_process()
        # Clean up temp audio file
        if audio_path and os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
                logger.info(f"Cleaned up temp file: {audio_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {audio_path}: {e}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'modules': {
            'asr': asr is not None,
            'translator': translator is not None,
            'tts': tts is not None
        },
        'active_processes': processor.active_processes,
        'max_concurrent': processor.max_concurrent,
        'cache_size': len(translation_cache),
        'audio_files': len(audio_cache)
    })

@app.route('/clear-cache', methods=['POST'])
def clear_cache():
    """Clear translation cache"""
    global translation_cache, audio_cache
    translation_cache.clear()
    audio_cache.clear()
    clean_audio_files()
    return jsonify({'status': 'success', 'message': 'Cache cleared'})

# Error handlers
@app.errorhandler(413)
def too_large(e):
    return jsonify({
        'status': 'error',
        'message': 'File too large. Maximum size is 10MB.'
    }), 413

@app.errorhandler(429)
def too_many_requests(e):
    return jsonify({
        'status': 'error',
        'message': 'Too many requests. Please try again later.'
    }), 429

@app.errorhandler(500)
def internal_error(e):
    return jsonify({
        'status': 'error',
        'message': 'Internal server error. Please try again.'
    }), 500

if __name__ == '__main__':
    # Create required directories
    os.makedirs('static/audio', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # Start cleanup thread
    def periodic_cleanup():
        while True:
            time.sleep(300)  # Clean every 5 minutes
            clean_audio_files()
    
    cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
    cleanup_thread.start()
    
    logger.info("Starting TalkLingo server...")
    logger.info(f"Modules status - ASR: {'✓' if asr else '✗'}, Translator: {'✓' if translator else '✗'}, TTS: {'✓' if tts else '✗'}")
    
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)