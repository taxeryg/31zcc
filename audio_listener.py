"""
audio_listener.py — Kick yayınlarından canlı ses çekip metne dönüştürme modülü
"""
import threading
import time
import logging
import requests
import json

logger = logging.getLogger(__name__)

class AudioListener:
    def __init__(self, socketio=None):
        self.socketio = socketio
        self.channel = None
        self.running = False
        self.thread = None
        self.history = []

    def start(self, channel_name: str):
        if self.running:
            self.stop()
            time.sleep(0.5)

        self.channel = channel_name.strip()
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.running = False

    def _listen_loop(self):
        logger.info(f"AudioListener started for {self.channel}")
        self._emit_status('connecting', f'Yayına bağlanılıyor: {self.channel}...')

        while self.running:
            try:
                # 1. Get channel info and playback URL
                url = f"https://kick.com/api/v2/channels/{self.channel}"
                resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                if resp.status_code != 200:
                    self._emit_status('error', f'Kanal bulunamadı veya yayın kapalı ({self.channel})')
                    time.sleep(10)
                    continue

                data = resp.json()
                if not data.get('livestream'):
                    self._emit_status('offline', f'{self.channel} şu an yayında değil (offline)')
                    time.sleep(10)
                    continue

                hls_url = data.get('playback_url')
                if not hls_url:
                    self._emit_status('error', 'Yayın akış adresi (HLS) alınamadı')
                    time.sleep(10)
                    continue

                self._emit_status('connected', f'Yayın sesi canlı dinleniyor 🟢 ({self.channel})')

                # Get low-res variant playlist
                master_resp = requests.get(hls_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                variant_url = None
                for line in master_resp.text.splitlines():
                    if line.startswith('http') and '.m3u8' in line:
                        variant_url = line
                        break

                if not variant_url:
                    variant_url = hls_url

                seen_segments = set()
                while self.running:
                    try:
                        playlist_resp = requests.get(variant_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                        segments = [l for l in playlist_resp.text.splitlines() if l.startswith('http') and '.ts' in l]

                        new_segments = [s for s in segments if s not in seen_segments]
                        if not new_segments and segments:
                            new_segments = [segments[-1]]

                        for seg_url in new_segments[-2:]:
                            seen_segments.add(seg_url)
                            if len(seen_segments) > 100:
                                seen_segments.clear()

                            # Transcribe audio segment via Speech-to-Text / Mock Demo
                            # For fast demo in browser without heavy local PyTorch GPU model:
                            self._transcribe_segment(seg_url)

                        time.sleep(4)
                    except Exception as e:
                        logger.error(f"Audio chunk loop error: {e}")
                        time.sleep(5)

            except Exception as e:
                logger.error(f"AudioListener loop error: {e}")
                self._emit_status('error', f'Hata: {e}')
                time.sleep(8)

    def _transcribe_segment(self, seg_url):
        import speech_recognition as sr
        import tempfile
        import subprocess
        import os
        import imageio_ffmpeg

        try:
            # Download actual live audio segment with headers
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            resp = requests.get(seg_url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return

            # Save temporary TS file
            with tempfile.NamedTemporaryFile(suffix='.ts', delete=False) as f_ts:
                f_ts.write(resp.content)
                ts_path = f_ts.name

            wav_path = ts_path.replace('.ts', '.wav')
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

            # Convert TS audio to WAV using imageio_ffmpeg with vocal frequency bandpass filter (highpass=200Hz, lowpass=3400Hz, volume gain)
            # This filters out background music bass, high trebles and keeps human voice frequencies
            res = subprocess.run([
                ffmpeg_exe, '-y', '-i', ts_path,
                '-af', 'highpass=f=200, lowpass=f=3400, volume=1.5',
                '-ac', '1', '-ar', '16000', wav_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)

            text = None
            if os.path.exists(wav_path) and os.path.getsize(wav_path) > 1000:
                r = sr.Recognizer()
                r.energy_threshold = 300  # Ignore background music noise below voice energy threshold
                r.dynamic_energy_threshold = True
                with sr.AudioFile(wav_path) as source:
                    audio_data = r.record(source)
                    text = r.recognize_google(audio_data, language='tr-TR')

            # Cleanup temp files
            for p in [ts_path, wav_path]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

            if text:
                item = {
                    'timestamp': time.strftime('%H:%M:%S'),
                    'channel': self.channel,
                    'text': text
                }
                self.history.append(item)
                if len(self.history) > 100:
                    self.history.pop(0)

                if self.socketio:
                    self.socketio.emit('audio_transcript', item)
        except Exception as e:
            logger.debug(f"Transcription detail (silent/no speech): {e}")

    def _emit_status(self, status, msg):
        if self.socketio:
            self.socketio.emit('audio_status', {'status': status, 'message': msg})
