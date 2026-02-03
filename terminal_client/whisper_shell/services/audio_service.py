import numpy as np
import sounddevice as sd
import asyncio
from loguru import logger
from ..services.config_service import cfg

class AudioService:
    """
    Service for capturing audio from the primary input device.
    Strictly outputs 16kHz, Mono, 16-bit PCM.
    """
    def __init__(self, loop, audio_queue):
        self.loop = loop
        self.audio_queue = audio_queue
        self.device_rate = 16000
        self.is_recording = False
        self.stream = None

    def audio_callback(self, indata, frames, time, status):
        """Callback for sounddevice InputStream."""
        if status: 
            logger.warning(f"Audio Callback Status: {status}")
            
        if self.is_recording:
            # Resample if needed
            if self.device_rate != 16000:
                duration = len(indata) / self.device_rate
                new_len = int(duration * 16000)
                # Linear interpolation for resampling (fast, decent quality for speech)
                audio = np.interp(
                    np.linspace(0, duration, new_len), 
                    np.linspace(0, duration, len(indata)), 
                    indata.flatten()
                )
            else:
                audio = indata.flatten()
            
            # Convert float32 -> int16 PCM (Normalized)
            pcm_data = (audio * 32767).astype(np.int16).tobytes()
            
            # Queue for Async Processing in the main loop
            self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, pcm_data)

    def start_stream(self):
        """Starts the hardware audio input stream."""
        if self.stream: 
            return
        
        try:
            # Query device info
            device_id = cfg.AUDIO_DEVICE_ID
            info = sd.query_devices(device_id, 'input')
            self.device_rate = int(info.get('default_samplerate', 16000))
            
            self.stream = sd.InputStream(
                samplerate=self.device_rate,
                channels=1,
                callback=self.audio_callback,
                device=device_id
            )
            self.stream.start()
            host_api_name = sd.query_hostapis(info['hostapi'])['name']
            logger.success(f"Audio Stream Active: [{device_id}] {info['name']} | {host_api_name} ({self.device_rate}Hz → 16000Hz)")
        except Exception as e:
            logger.critical(f"Failed to start hardware audio stream: {e}")
            raise e

    def stop_stream(self):
        """Closes hardware stream."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            logger.info("Audio Stream Shutdown.")

    def start_capture(self):
        """Enable data propagation to the queue."""
        self.is_recording = True
    
    def stop_capture(self):
        """Disable data propagation to the queue."""
        self.is_recording = False
