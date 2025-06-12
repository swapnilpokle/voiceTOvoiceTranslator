from faster_whisper import WhisperModel
import sounddevice as sd
import numpy as np
import wavio 
import os

class ASRModule:
    def __init__(self):
        self.model_size = "base"
        self.model = WhisperModel(self.model_size, compute_type="int8")
        
    def record_audio(self, duration=5, sample_rate=44100):
        """Record audio from microphone"""
        print(f"Recording for {duration} seconds...")
        recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1)
        sd.wait()
        return recording, sample_rate
    
    def save_audio(self, recording, sample_rate, filename="temp_recording.wav"):
        """Save recorded audio to file"""
        wavio.write(filename, recording, sample_rate, sampwidth=2)
        return filename
    
    def transcribe_audio(self, audio_path):
        """Transcribe audio file to text"""
        segments, info = self.model.transcribe(audio_path, beam_size=5)
        transcription = " ".join([segment.text for segment in segments])
        return transcription, info.language