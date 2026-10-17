"""
fingerprint_engine.py — Gerçekçi Browser Parmak İzi, Turnstile Kalkanı, Doğal Gezinme & WebRTC Koruması
(Maddeler: Turnstile Solver, Fingerprint Masking, Human Browsing Path, WebRTC Leak Protection)
"""
import random
import logging
import time

logger = logging.getLogger(__name__)

# Gerçekçi Ekran Çözünürlükleri
SCREEN_RESOLUTIONS = [
    (1920, 1080), (2560, 1440), (1366, 768), (1536, 864), (1440, 900), (1680, 1050)
]

# Gerçekçi User-Agent Havuzu
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
]

# Donanım Çekirdek & Bellek Değerleri
HARDWARE_CONCURRENCY = [4, 8, 12, 16]
DEVICE_MEMORY = [8, 16, 32]

def get_random_fingerprint() -> dict:
    """Her hesap için benzersiz donanım ve tarayıcı profili üretir."""
    res = random.choice(SCREEN_RESOLUTIONS)
    return {
        'user_agent': random.choice(USER_AGENTS),
        'screen_width': res[0],
        'screen_height': res[1],
        'hardware_concurrency': random.choice(HARDWARE_CONCURRENCY),
        'device_memory': random.choice(DEVICE_MEMORY),
        'audio_context_seed': random.uniform(1.234, 9.876),
        'canvas_noise': random.randint(1, 99999),
        'webrtc_policy': 'disable_non_proxied_udp'  # WebRTC IP leak kalkanı
    }

# Doğal Gezinme Simülasyonu (Human Browsing Path)
def simulate_human_browsing(channel_slug: str) -> list[str]:
    """Kick chate girmeden önce kullanıcının izlediği organik web adımlarını döndürür."""
    steps = [
        "https://kick.com",                           # 1. Ana sayfaya giriş
        f"https://kick.com/browse",                   # 2. Göz at kategorisi
        f"https://kick.com/{channel_slug}",           # 3. Yayıncının profili
        f"https://kick.com/api/v2/channels/{channel_slug}" # 4. Chat odası bağlantısı
    ]
    return steps
