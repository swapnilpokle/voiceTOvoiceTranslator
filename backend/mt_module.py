# (Your existing gemini-edit-harsh-2-abhi.ipynb code converted to a class)
# This would be the PreloadedTranslator class from your notebook
# I'll keep the original implementation since it's quite comprehensive
import nltk
import os
import pickle
import re
import time
from nltk.tokenize import word_tokenize
from rank_bm25 import BM25Okapi
from langdetect import detect
import logging
from typing import List, Tuple, Dict
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
import gc  # For memory management

# Download required NLTK resources
try:
    nltk.download('punkt', quiet=True)
except:
    pass

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize cache for repeated queries
translation_cache = {}
MAX_CACHE_SIZE = 100

# Language names for Indian languages
LANGUAGE_NAMES = {
    "English": "English", "Hindi": "Hindi", "Bengali": "Bengali", "Tamil": "Tamil",
    "Telugu": "Telugu", "Marathi": "Marathi", "Kannada": "Kannada", "Malayalam": "Malayalam",
    "Punjabi": "Punjabi", "Gujarati": "Gujarati", "Odia": "Odia", "Urdu": "Urdu",
    "Assamese": "Assamese", "Konkani": "Konkani", "Sindhi": "Sindhi", "Sanskrit": "Sanskrit"
}

# Language detection mapping
LANG_DETECT_MAP = {
    'en': 'English', 'hi': 'Hindi', 'bn': 'Bengali', 'ta': 'Tamil', 'te': 'Telugu',
    'mr': 'Marathi', 'kn': 'Kannada', 'ml': 'Malayalam', 'pa': 'Punjabi', 
    'gu': 'Gujarati', 'or': 'Odia', 'ur': 'Urdu', 'as': 'Assamese'
}

# Language detection patterns
LANGUAGE_PATTERNS = {
    'Devanagari': re.compile(r'[\u0900-\u097F]'),
    'Bengali': re.compile(r'[\u0980-\u09FF]'),
    'Gujarati': re.compile(r'[\u0A80-\u0AFF]'),
    'Punjabi': re.compile(r'[\u0A00-\u0A7F]'),
    'Tamil': re.compile(r'[\u0B80-\u0BFF]'),
    'Telugu': re.compile(r'[\u0C00-\u0C7F]'),
    'Kannada': re.compile(r'[\u0C80-\u0CFF]'),
    'Malayalam': re.compile(r'[\u0D00-\u0D7F]'),
    'Odia': re.compile(r'[\u0B00-\u0B7F]'),
    'Urdu': re.compile(r'[\u0600-\u06FF]')
}

SCRIPT_TO_LANGUAGE = {
    'Devanagari': ['Hindi', 'Marathi', 'Sanskrit'],
    'Bengali': ['Bengali', 'Assamese'],
    'Gujarati': ['Gujarati'], 'Punjabi': ['Punjabi'], 'Tamil': ['Tamil'],
    'Telugu': ['Telugu'], 'Kannada': ['Kannada'], 'Malayalam': ['Malayalam'],
    'Odia': ['Odia'], 'Urdu': ['Urdu']
}


class PreloadedTranslator:
    def __init__(self, datasets_dir=None, gemini_api_key=None):
        print("🚀 Starting Preloaded Multilingual Translator...")
        
        # Setup API
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        if not self.gemini_api_key:
            raise ValueError("Gemini API key is required.")
        
        print("🔧 Configuring Gemini API...")
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        print("✅ Gemini API ready!")
        
        # Preload all datasets
        self.datasets_dir = datasets_dir or "./datasets"
        self.loaded_datasets = {}  # Store all datasets in memory
        
        print("📁 Loading all datasets...")
        self._load_all_datasets()
        
        if self.loaded_datasets:
            print(f"✅ Loaded {len(self.loaded_datasets)} dataset pairs")
            for pair, data in self.loaded_datasets.items():
                print(f"  📄 {pair}: {len(data['source'])} sentence pairs")
        else:
            print("⚠️  No datasets found - using Gemini-only mode")
    
    def _load_all_datasets(self):
        """Load all available datasets at startup"""
        try:
            # Check multiple possible locations
            possible_dirs = [
                self.datasets_dir,
                "../input",
                "./",
                "../datasets",
                "/kaggle/input"
            ]
            
            dataset_files = []
            
            for base_dir in possible_dirs:
                if not os.path.exists(base_dir):
                    continue
                
                # Check direct files
                if os.path.isdir(base_dir):
                    for filename in os.listdir(base_dir):
                        if filename.endswith('.pkl'):
                            dataset_files.append(os.path.join(base_dir, filename))
                
                # Check subdirectories in Kaggle
                if "kaggle" in base_dir and os.path.exists(base_dir):
                    for subdir in os.listdir(base_dir):
                        subdir_path = os.path.join(base_dir, subdir)
                        if os.path.isdir(subdir_path):
                            for filename in os.listdir(subdir_path):
                                if filename.endswith('.pkl'):
                                    dataset_files.append(os.path.join(subdir_path, filename))
            
            # Load each valid dataset
            for filepath in dataset_files:
                self._load_single_dataset(filepath)
                    
        except Exception as e:
            print(f"Error loading datasets: {e}")
    
    def _load_single_dataset(self, filepath):
        """Load a single dataset file"""
        try:
            filename = os.path.basename(filepath)
            name_parts = os.path.splitext(filename)[0].split('_')
            
            if len(name_parts) >= 2:
                lang1 = name_parts[0].title()
                lang2 = name_parts[1].title()
                
                if lang1 in LANGUAGE_NAMES and lang2 in LANGUAGE_NAMES:
                    print(f"  📥 Loading {lang1}-{lang2}...")
                    
                    with open(filepath, 'rb') as f:
                        data = pickle.load(f)
                    
                    source_key = lang1.lower()
                    target_key = lang2.lower()
                    
                    if "dataset" in data and source_key in data["dataset"] and target_key in data["dataset"]:
                        # Load all sentences without limit
                        source_sentences = data["dataset"][source_key]
                        target_sentences = data["dataset"][target_key]
                        
                        # Use pre-built BM25 index if available
                        if "bm25_index" in data and source_key in data["bm25_index"]:
                            bm25_index = data["bm25_index"][source_key]
                        else:
                            # Fallback: create BM25 index if not present
                            source_tokens = [word_tokenize(s.lower()) for s in source_sentences]
                            bm25_index = BM25Okapi(source_tokens)
                        
                        # Store both directions
                        pair_key_1 = f"{lang1}-{lang2}"
                        pair_key_2 = f"{lang2}-{lang1}"
                        
                        dataset_1 = {
                            'source': source_sentences,
                            'target': target_sentences,
                            'bm25': bm25_index,
                            'source_lang': lang1,
                            'target_lang': lang2
                        }
                        
                        # Create reverse dataset
                        if "bm25_index" in data and target_key in data["bm25_index"]:
                            reverse_bm25 = data["bm25_index"][target_key]
                        else:
                            target_tokens = [word_tokenize(s.lower()) for s in target_sentences]
                            reverse_bm25 = BM25Okapi(target_tokens)
                        
                        dataset_2 = {
                            'source': target_sentences,
                            'target': source_sentences,
                            'bm25': reverse_bm25,
                            'source_lang': lang2,
                            'target_lang': lang1
                        }
                        
                        self.loaded_datasets[pair_key_1] = dataset_1
                        self.loaded_datasets[pair_key_2] = dataset_2
                        
                        print(f"    ✅ {pair_key_1}: {len(source_sentences)} pairs")
                        print(f"    ✅ {pair_key_2}: {len(target_sentences)} pairs")
                        
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
    
    def detect_language(self, text: str) -> str:
        """Detect language of input text"""
        # Script-based detection first
        for script, pattern in LANGUAGE_PATTERNS.items():
            if pattern.search(text):
                possible_languages = SCRIPT_TO_LANGUAGE.get(script, [])
                if len(possible_languages) == 1:
                    return possible_languages[0]
                # Try langdetect for disambiguation
                try:
                    lang_code = detect(text)
                    detected = LANG_DETECT_MAP.get(lang_code)
                    if detected in possible_languages:
                        return detected
                    return possible_languages[0]
                except:
                    return possible_languages[0]
        
        # Fallback to langdetect
        try:
            lang_code = detect(text)
            return LANG_DETECT_MAP.get(lang_code, "English")
        except:
            return "English"
    
    def _get_examples(self, query: str, source_lang: str, target_lang: str, top_k: int = 3) -> List[Tuple[str, str]]:
        """Get relevant translation examples from preloaded datasets"""
        pair_key = f"{source_lang}-{target_lang}"
        
        if pair_key not in self.loaded_datasets:
            return []
        
        try:
            dataset = self.loaded_datasets[pair_key]
            query_tokens = word_tokenize(query.lower())
            scores = dataset['bm25'].get_scores(query_tokens)
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
            
            source_sentences = dataset['source']
            target_sentences = dataset['target']
            
            return [(source_sentences[idx], target_sentences[idx]) for idx in top_indices if idx < len(source_sentences)]
            
        except Exception as e:
            print(f"Error getting examples: {e}")
            return []
    
    def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(
                    prompt,
                    generation_config=GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=100,
                        top_p=0.9
                    )
                )
                return response.text.strip()
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"Retry {attempt + 1}/{max_retries}...")
                    time.sleep(1)
                else:
                    print(f"Gemini API error: {e}")
                    return ""
    
    def translate(self, text: str, source_lang: str = None, target_lang: str = None) -> str:
        """Translate text with examples from preloaded datasets"""
        # Auto-detect source language
        if not source_lang:
            source_lang = self.detect_language(text)
        
        # Check cache
        cache_key = f"{text[:50]}:{source_lang}:{target_lang}"
        if cache_key in translation_cache:
            return translation_cache[cache_key]
        
        # Get examples from preloaded datasets
        examples = self._get_examples(text, source_lang, target_lang, top_k=3)
        
        # Build prompt with examples
        prompt = f"""Translate the following text from {source_lang} to {target_lang}.
Provide ONLY the translation, without any additional explanations, notes, or formatting.
Do not include the original text or language names in the response.
The response must be ONLY the translated text in {target_lang}.

Text to translate: "{text}"
"""
        
        # Add examples if available
        if examples:
            prompt += f"\nHere are some reference translation examples from {source_lang} to {target_lang} (use these for context, but do not include them in your response):\n"
            for i, (src, tgt) in enumerate(examples, 1):
                prompt += f"Example {i}: \"{src}\" → \"{tgt}\"\n"
        
        prompt += f"\n{target_lang} translation:"
        
        # Get translation
        translation = self._call_gemini(prompt)
        
        # Clean up the response
        if translation:
            translation = translation.strip('"\'')
            translation = translation.split('\n')[0].strip()
            if ":" in translation:
                translation = translation.split(":")[-1].strip()
            
            # Cache with size limit
            if len(translation_cache) >= MAX_CACHE_SIZE:
                for _ in range(20):
                    translation_cache.pop(next(iter(translation_cache)), None)
            translation_cache[cache_key] = translation
        
        return translation
    
    def get_available_languages(self, source_lang: str) -> List[str]:
        """Get available target languages for a given source language"""
        targets = set()
        for pair_key in self.loaded_datasets.keys():
            lang1, lang2 = pair_key.split('-')
            if lang1 == source_lang:
                targets.add(lang2)
        return sorted(list(targets))
    
    def get_all_language_pairs(self) -> List[str]:
        """Get all available language pairs"""
        return sorted(list(self.loaded_datasets.keys()))
    
    def get_dataset_info(self) -> Dict[str, int]:
        """Get information about loaded datasets"""
        info = {}
        for pair, data in self.loaded_datasets.items():
            info[pair] = len(data['source'])
        return info
    
    def translate_with_detection(self, text: str, target_lang: str) -> str:
        """Auto-detect source language and translate to target"""
        source_lang = self.detect_language(text)
        return self.translate(text, source_lang, target_lang)

class MTModule:
    def __init__(self, gemini_api_key):
        self.translator = PreloadedTranslator(gemini_api_key=gemini_api_key)
    
    def translate(self, text, source_lang=None, target_lang=None):
        return self.translator.translate(text, source_lang, target_lang)
    
    def detect_language(self, text):
        return self.translator.detect_language(text)
    
    def get_available_targets(self, source_lang):
        return self.translator.get_available_languages(source_lang)