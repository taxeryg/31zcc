"""
ocr_engine.py — Kick yayın ekranı ve görsel analiz motoru
Yayından veya kullanıcıdan gelen ekran görüntüsünü AI ile analiz eder.
"""
import base64
import io
import logging
import requests
import openai
from PIL import Image

logger = logging.getLogger(__name__)

def analyze_livestream_frame(image_bytes: bytes, api_key: str, base_url: str = 'https://api.openai.com/v1', model: str = 'gpt-4o-mini') -> str:
    """
    Analyzes livestream screenshot using Vision AI.
    Handles death, victory, score, case opening (Madde 66), and webcam issues (Madde 64).
    """
    try:
        # Resize image if too large to save tokens/bandwidth
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((800, 800))
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        b64_img = base64.b64encode(buf.getvalue()).decode('utf-8')

        client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=25)
        prompt = (
            "Sen Kick.com yayınını izleyen samimi bir izleyicisin. "
            "Bu ekran görüntüsüne dikkatle bak:\n"
            "- Eğer ekranda bir KASA veya SANDIK AÇILIŞI (CS2/Valorant vb.) varsa: Heyecanlı ol, 'bıçak geliyor hissediyorum', 'hadi be sarı ver', 'bize çıkmaz zaten' gibi tepki ver.\n"
            "- Eğer WEBCAM veya KAMERA DONMUŞ/KARARMIŞ görünüyorsa: 'abi cam dondu galiba', 'kamera takıldı abi' şeklinde ikaz et.\n"
            "- Normal oyunsa: Oyun skoru, ölüm, zafer hakkında 1-5 kelimelik çok kısa, noktalama işaretsiz yorum yap (örn: 'helal be aldınız', 'f abi', 'skor kaç kaç oldu', 'ggwp')."
        )

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                        }
                    ]
                }
            ],
            max_tokens=50,
            temperature=0.85
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Vision OCR analysis error: {e}")
        return ""


def request_kick_clip(channel_id: int, bearer_token: str) -> tuple[bool, str]:
    """Madde 68: Kick Canlı Klip Alma Emri (API Clip Request)."""
    token = bearer_token.strip().replace('Bearer ', '')
    url = f"https://kick.com/api/v2/channels/{channel_id}/clips"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
    }
    try:
        r = requests.post(url, headers=headers, json={}, timeout=8)
        return r.status_code in (200, 201), r.text
    except Exception as e:
        logger.error(f"request_kick_clip error: {e}")
        return False, str(e)
