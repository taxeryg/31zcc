"""
ai_engine.py — AI API entegrasyonu, karakter prompt yönetimi, bot seçimi
"""
import logging
import random
import re

import openai

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# System Prompt Builder
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# Typo Generator (1 in 30 chance)
# ──────────────────────────────────────────────

_NEARBY_KEYS = {
    'a': 's', 's': 'a', 'd': 's', 'e': 'w', 'r': 'e', 't': 'r',
    'k': 'l', 'l': 'k', 'm': 'n', 'n': 'm', 'o': 'p', 'p': 'o',
    'i': 'ı', 'ı': 'i', 'u': 'y', 'y': 'u', 'c': 'v', 'v': 'c'
}

def apply_human_typo(text: str, chance: float = 1/30) -> str:
    """Simulates realistic human keyboard typos roughly once in 30 messages."""
    if not text or len(text) < 4:
        return text
    if random.random() > chance:
        return text

    idx = random.randint(1, len(text) - 2)
    char = text[idx].lower()
    if char in _NEARBY_KEYS:
        rep = _NEARBY_KEYS[char]
        return text[:idx] + rep + text[idx+1:]
    return text


# ──────────────────────────────────────────────
# Keyword Trigger Engine (Hızlı Doğal Replikler)
# ──────────────────────────────────────────────

KEYWORD_TRIGGERS = {
    'çekiliş': ['çekiliş ne zaman beyler', 'katıldık bakalım', 'bize çıkmaz'],
    'dc': ['dc linki bio da var kanka', 'discordda ses var mı'],
    'insta': ['instası açıklamada yazıyor', 'insta story atmış mı'],
    'drop': ['drop var mı yayında', 'drops açık mı'],
    'dondu': ['bende donmadı kanka f5 at', 'yayın akıcı bende', 'ufak takıldı geldi'],
    'ses yok': ['ses geliyor kanka', 'kulaklığı kontrol et'],
}

def check_keyword_trigger(content: str) -> str | None:
    cl = content.lower()
    for kw, replies in KEYWORD_TRIGGERS.items():
        if kw in cl:
            return random.choice(replies)
    return None


# Doğal Türk internet random kahkahaları (Madde 62)
TURKISH_RANDOM_LAUGHS = [
    "ahahah", "sadasdas", "koptum amk", "DKJASGDJSAGD", "asdasfads", "harbi mi lan ahahah"
]

def build_system_prompt(bot: dict, sentiment: str = 'neutral', bot_role: str = None, regional_dialect: str = None, is_derby_day: bool = False) -> str:
    custom = (bot.get('system_prompt') or '').strip()
    if custom:
        return custom

    mood_note = ""
    if sentiment == 'hype':
        mood_note = "Chat şu an çok coşkulu ve hype! Sen de heyecanlı ve enerjik katıl."
    elif sentiment == 'toxic':
        mood_note = "Chatte gerginlik var, ortalığı yumuşat veya taşak geçerek olayı dağıt."

    # Madde 53: Futbol / Derbi Gündemi
    derby_note = ""
    if is_derby_day or random.random() < 0.12:
        derby_note = "\nGündem Notu (Madde 53): Bugün maç/derbi günü havası var, araya bazen hafif futbol lafı veya skor muhabbeti sıkıştırabilirsin ('maçı izledin mi', 'gs mi fb mi', 'hakem doğradı valla')."

    # Madde 77: Bölgesel Dil & Ağız Adaptasyonu
    dialect_note = ""
    if regional_dialect == 'ege':
        dialect_note = "\nŞive/Ağız Notu (Madde 77 - Ege): Arada hafif Ege ağzı kullan ('gari', 'nörüyon', 'bakar mısın gari', 'geliver')."
    elif regional_dialect == 'karadeniz':
        dialect_note = "\nŞive/Ağız Notu (Madde 77 - Karadeniz): Arada Karadeniz şivesi esintisi kat ('ula', 'da', 'habu', 'uşağum', 'hade da')."

    personality = bot.get('personality', 'Samimi izleyici')

    return f"""Sen "{bot['name']}" adında Kick.com chatinde takılan samimi bir botsun.
Karakterin ve Rolün: {personality}
{mood_note}{derby_note}{dialect_note}

## KONUŞMA VE ÜSLUP KURALLARI (ÇOK ÖNEMLİ):
1. CHAT KISALTMALARINI BİL VE UYGULA:
   - "sa" = "selamın aleyküm" / "selam" demektir.
   - "as" = "aleyküm selam", "hg" = "hoş geldin", "hb" = "hoş bulduk", "eyv" = "eyvallah" anlamındadır.
2. Kesinlikle RESMİ ve KİBAR DİL KULLANMA! ("Selam! İyiyim sağol, sen nasılsın?" gibi robotik cümleler ASLA KURMA).
3. Gerçek bir Kick chat kullanıcısı gibi samimi, rahat ve sokağın diliyle yaz.
4. Noktalama işaretlerine (nokta, virgül vb.) UYMA, büyük-küçük harf kurallarına dikkat ETME (küçük harflerle rahat yaz).
5. Mesajların 1 ile 5 kelime arasında ÇOK KISA olsun. Uzun laf kalabalığı yapma.
6. Örnek konuşma tarzları: "as hg kanka", "nörüyon", "iyidir senden naber", "eyv kanka", "valla aynen", "as hg", "ahahah harbi mi", "koptum amk".
7. Yayıncıya bazen destek çık ("hadi be abi sen alırsın"), bazen hafif takıl ("yine mi öldün ya").
8. Komik durumlarda random gülüş at ("asdsad", "koptum amk").
9. Prefix ([İsim]: vb.) veya tırnak işareti KULLANMA, sadece direkt mesajı yaz."""


# ──────────────────────────────────────────────
# Context Builder
# ──────────────────────────────────────────────

def build_context_messages(chat_history: list, incoming: dict, bot_name: str, user_mem: dict = None) -> list:
    messages = []
    # Last 15 messages as context
    for msg in list(chat_history)[-15:]:
        content_text = msg.get('content', '')
        uname = msg.get('username', 'bilinmiyor')
        mtype = msg.get('type', 'user')

        if mtype == 'bot':
            if msg.get('bot_name') == bot_name:
                messages.append({'role': 'assistant', 'content': content_text})
            else:
                messages.append({'role': 'user', 'content': f'[{msg.get("bot_name", uname)}] {content_text}'})
        else:
            messages.append({'role': 'user', 'content': f'[{uname}] {content_text}'})

    # User memory hint if returning chatter
    chatter_note = ""
    if user_mem and user_mem.get('message_count', 0) > 3:
        chatter_note = f" (Not: Bu izleyici chatin müdavimi, daha önce {user_mem['message_count']} mesaj yazdı)"

    # Add current triggering message
    messages.append({
        'role': 'user',
        'content': f'[{incoming["username"]}{chatter_note}] {incoming["content"]}'
    })
    return messages


# ──────────────────────────────────────────────
# Response Generator
# ──────────────────────────────────────────────

def generate_response(bot: dict, chat_history: list, incoming: dict,
                       api_key: str, base_url: str, model: str,
                       sentiment: str = 'neutral', user_mem: dict = None,
                       regional_dialect: str = None, is_derby_day: bool = False):
    """
    Returns (response_text, error_code | None)
    error_code: None = success, 'rate_limit', 'auth_error', 'timeout', str = other
    """
    # 1. Quick check for natural keyword trigger first (super fast and organic)
    if random.random() < 0.25:
        kw_reply = check_keyword_trigger(incoming.get('content', ''))
        if kw_reply:
            return apply_human_typo(kw_reply), None

    try:
        client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=20)
        system_prompt = build_system_prompt(bot, sentiment=sentiment, regional_dialect=regional_dialect, is_derby_day=is_derby_day)
        ctx = build_context_messages(chat_history, incoming, bot['name'], user_mem=user_mem)

        resp = client.chat.completions.create(
            model=model,
            messages=[{'role': 'system', 'content': system_prompt}, *ctx],
            max_tokens=120,
            temperature=0.88,
            presence_penalty=0.55,
            frequency_penalty=0.65,
        )
        text = resp.choices[0].message.content.strip()
        # Strip any accidental prefix like "[BotName]: " the model might add
        text = re.sub(r'^\[.*?\]\s*:?\s*', '', text).strip()
        # Apply 1/30 typo chance
        text = apply_human_typo(text, chance=1/30)
        return text, None

    except openai.RateLimitError:
        logger.warning(f'Rate limit hit for bot {bot["name"]}')
        return None, 'rate_limit'
    except openai.AuthenticationError:
        logger.error(f'Auth error for bot {bot["name"]}')
        return None, 'auth_error'
    except openai.APITimeoutError:
        logger.warning(f'Timeout for bot {bot["name"]}')
        return None, 'timeout'
    except Exception as e:
        logger.error(f'generate_response error: {e}')
        return None, str(e)[:100]


# ──────────────────────────────────────────────
# Message Analyzer
# ──────────────────────────────────────────────

_GREETINGS = {'sa', 'selam', 'merhaba', 'hey', 'naber', 'napıyorsunuz',
               'nasılsınız', 'herkese', 'herkese selam', 'günaydın', 'iyi geceler'}


def analyze_message(content: str, bots: list) -> dict:
    """Returns {bot_id: score} for each enabled bot."""
    cl = content.lower()
    words = set(re.findall(r'\w+', cl))
    scores = {}

    for bot in bots:
        if not bot.get('enabled'):
            continue
        score = 0.0
        bname = bot['name'].lower()
        bname_no_bot = bname.replace('bot', '').strip()

        # Direct mention bonus
        if bname in cl or (bname_no_bot and bname_no_bot in cl):
            score += 10.0

        # Interest match
        for kw in bot.get('interests', '').lower().split(','):
            kw = kw.strip()
            if kw and kw in cl:
                score += 2.5

        # Greeting
        if words & _GREETINGS:
            score += 0.8

        # Question mark — bots like to answer questions
        if '?' in content:
            score += 0.5

        scores[bot['id']] = score

    return scores


# ──────────────────────────────────────────────
# Bot Selector
# ──────────────────────────────────────────────

def select_bot(bots: list, message_content: str,
               cooldowns: dict, daily_counter: dict):
    """
    cooldowns: {bot_id: remaining_seconds}  — >0 means on cooldown
    daily_counter: {bot_id: count}

    Returns selected bot dict or None.
    """
    scores = analyze_message(message_content, bots)
    eligible = []

    for bot in bots:
        if not bot.get('enabled'):
            continue
        bid = bot['id']

        if cooldowns.get(bid, 0) > 0:
            continue

        if daily_counter.get(bid, 0) >= bot.get('daily_limit', 50):
            continue

        base_chance = float(bot.get('response_chance', 0.35))
        score_bonus = min(scores.get(bid, 0) * 0.04, 0.40)
        total_chance = min(base_chance + score_bonus, 0.95)

        if random.random() < total_chance:
            eligible.append((bot, scores.get(bid, 0)))

    if not eligible:
        return None

    # Sort by score + small random jitter, pick top
    eligible.sort(key=lambda x: x[1] + random.random() * 0.6, reverse=True)
    return eligible[0][0]


# ──────────────────────────────────────────────
# Token Validator
# ──────────────────────────────────────────────

def test_api_key(api_key: str, base_url: str, model: str):
    """Returns (valid: bool, message: str)"""
    try:
        client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=12)
        client.chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': 'ping'}],
            max_tokens=3,
        )
        return True, 'Geçerli ✓'
    except openai.AuthenticationError:
        return False, 'Geçersiz API anahtarı'
    except openai.RateLimitError:
        return False, 'Rate limit aşıldı (anahtar geçerli olabilir)'
    except openai.NotFoundError:
        return False, f'Model bulunamadı: {model}'
    except Exception as e:
        return False, str(e)[:120]
