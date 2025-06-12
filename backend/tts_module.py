import edge_tts
import asyncio
from typing import Dict

class TTSModule:
    def __init__(self):
        self.VOICE_MAP = {
            "en": "en-IN-NeerjaNeural",
            "mr": "mr-IN-AarohiNeural",
            "hi": "hi-IN-SwaraNeural",
            "ta": "ta-IN-PallaviNeural",
            "te": "te-IN-MohanNeural",
            "kn": "kn-IN-GaganNeural",
            "ml": "ml-IN-MidhunNeural",
            "bn": "bn-IN-BashkarNeural",
            "gu": "gu-IN-DhwaniNeural",
            "de": "de-DE-AmalaNeural",
            "ja": "ja-JP-KeitaNeural",
            "zh": "zh-CN-XiaoxiaoNeural",
            "ko": "ko-KR-InJoonNeural",
            "fr": "fr-FR-DeniseNeural"
        }
    
    async def text_to_speech(self, text: str, lang_code: str, output_file: str) -> None:
        voice = self.VOICE_MAP.get(lang_code.lower(), self.VOICE_MAP["en"])
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)
    
    def sync_text_to_speech(self, text: str, lang_code: str, output_file: str) -> None:
        asyncio.run(self.text_to_speech(text, lang_code, output_file))