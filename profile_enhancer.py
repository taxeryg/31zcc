"""
profile_enhancer.py — Kick hesapları için gerçekçi Pinterest estetiği avatarlar ve doğal Türkçe biyografiler (Madde 45)
"""
import random
import requests
import logging

logger = logging.getLogger(__name__)

# Gerçekçi Pinterest / Unsplash portre avatar havuzu (doğal insan, anime/gamer ve estetik)
PINTEREST_AVATARS = [
    "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=400&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=400&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=400&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1522075469751-3a6694fb2f61?w=400&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1488426862026-3ee34a7d66df?w=400&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=400&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=400&auto=format&fit=crop&q=80"
]

def generate_free_avatar_url(seed: str = None) -> str:
    """Madde 100: Tamamen ücretsiz API'lerle benzersiz dinamik avatar üretimi (DiceBear / UI-Avatars / Unsplash)."""
    if not seed:
        seed = str(random.randint(100000, 999999))
    styles = ['adventurer', 'avataaars', 'bottts', 'fun-emoji', 'lorelei', 'notionists']
    style = random.choice(styles)
    # DiceBear %50, Unsplash Pinterest %50
    if random.random() < 0.5:
        return f"https://api.dicebear.com/7.x/{style}/svg?seed={seed}"
    return random.choice(PINTEREST_AVATARS)

# Doğal, gerçekçi Türkçe Kick biyografi şablonları
NATURAL_TURKISH_BIOS = [
    "Sadece yayın izleyip kafa dağıtıyorum ☕",
    "Oyun, muhabbet, gece mesaisi... 🎮",
    "Takılıyoruz öyle buralarda.",
    "Buraların yabancısı değiliz ✌️",
    "Valorant & CS2 bağımlısı bir garip izleyici.",
    "Yayın sarıyor, çaylar taze.",
    "Laf aramızda geceleri buralardayız.",
    "Gündüz iş, gece Kick.",
    "sessizce izleyenlerden.",
    "iyi oyun, bol makara.",
    "öylesine bir profil.",
    "buralardayız kardeş.",
    "futbol, yayın, chill takılmaca ⚽",
    "yayıncı kazansın diye dua edenler derneği.",
    "gece 3 mesaisi bitti, yayındayız.",
    "sohbet sararsa yazarım yoksa lurk 💤"
]

def get_random_profile(username: str = None):
    """Returns realistic avatar URL and bio."""
    return {
        'avatar_url': generate_free_avatar_url(username),
        'bio': random.choice(NATURAL_TURKISH_BIOS)
    }

def update_kick_profile(bearer_token: str, bio: str = None, avatar_url: str = None) -> tuple[bool, str]:
    """Updates Kick account profile info (Bio & Socials) using Kick API."""
    token = bearer_token.strip()
    if token.startswith("Bearer "):
        token = token[7:].strip()
    
    url = "https://kick.com/api/v1/user"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0"
    }
    payload = {}
    if bio:
        payload["bio"] = bio

    try:
        r = requests.put(url, headers=headers, json=payload, timeout=8)
        return r.status_code == 200, r.text
    except Exception as e:
        logger.error(f"update_kick_profile error: {e}")
        return False, str(e)
