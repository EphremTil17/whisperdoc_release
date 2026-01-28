import numpy as np
import sounddevice as sd
import asyncio
from loguru import logger
from .config import cfg

class AudioManager:
    def __init__(self, loop, audio_queue):
        self.loop = loop
        self.audio_queue = audio_queue
        self.device_rate = 16000
        self.is_recording = False
        self.stream = None

    def audio_callback(self, indata, frames, time, status):
        """Callback for sounddevice InputStream."""
        if status: logger.warning(status)
        if self.is_recording:
            # Resample if needed
            if self.device_rate != 16000:
                duration = len(indata) / self.device_rate
                new_len = int(duration * 16000)
                # Linear interpolation for resampling (fast, decent quality for speech)
                audio = np.interp(np.linspace(0, duration, new_len), np.linspace(0, duration, len(indata)), indata.flatten())
            else:
                audio = indata.flatten()
            
            # Convert float32 -> int16 PCM
            pcm_data = (audio * 32767).astype(np.int16).tobytes()
            
            # Queue for Async Processing
            self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, pcm_data)

    def start_stream(self):
        """Starts the audio input stream."""
        if self.stream: return
        
        try:
            # Query device info
            info = sd.query_devices(cfg.AUDIO_DEVICE_ID, 'input')
            self.device_rate = int(info.get('default_samplerate', 16000))
            
            self.stream = sd.InputStream(
                samplerate=self.device_rate,
                channels=1,
                callback=self.audio_callback,
                device=cfg.AUDIO_DEVICE_ID
            )
            self.stream.start()
            logger.success(f"Mic Ready: {info['name']} ({self.device_rate}Hz)")
        except Exception as e:
            logger.critical(f"Audio Device Error: {e}")
            raise e

    def stop_stream(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()

    def start_recording(self):
        self.is_recording = True
    
    def stop_recording(self):
        self.is_recording = False
