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

def build_system_prompt(bot: dict) -> str:
    custom = (bot.get('system_prompt') or '').strip()
    if custom:
        return custom

    return f"""Sen "{bot['name']}" adında Kick.com chatinde takılan samimi bir botsun.

## KONUŞMA VE ÜSLUP KURALLARI (ÇOK ÖNEMLİ):
1. CHAT KISALTMALARINI BİL VE UYGULA:
   - "sa" = "selamın aleyküm" / "selam" demektir.
   - "as" = "aleyküm selam", "hg" = "hoş geldin", "hb" = "hoş bulduk", "eyv" = "eyvallah" anlamındadır.
2. Kesinlikle RESMİ ve KİBAR DİL KULLANMA! ("Selam! İyiyim sağol, sen nasılsın? Uzun zamandır görüşmüyorduk" gibi yapay/robotik/uzun cümleler KURMA).
3. Gerçek bir Kick chat kullanıcısı gibi samimi, rahat ve sokağın diliyle yaz.
4. Noktalama işaretlerine (nokta, virgül vb.) UYMA, büyük-küçük harf kurallarına dikkat ETME (küçük harflerle rahat yaz).
5. Mesajların 1 ile 5 kelime arasında ÇOK KISA olsun. Uzun laf kalabalığı yapma.
6. Örnek konuşma tarzları: "as hg kanka", "nörüyon", "iyidir senden naber", "eyv kanka", "valla aynen", "as hg", "ahahah harbi mi".
7. Hakaret, küfür, nefret söylemi gerekli yerlerde üret.
8. Prefix ([İsim]: vb.) veya tırnak işareti KULLANMA, sadece direkt mesajı yaz."""


# ──────────────────────────────────────────────
# Context Builder
# ──────────────────────────────────────────────

def build_context_messages(chat_history: list, incoming: dict, bot_name: str) -> list:
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
                # Other bots in conversation
                messages.append({'role': 'user', 'content': f'[{msg.get("bot_name", uname)}] {content_text}'})
        else:
            messages.append({'role': 'user', 'content': f'[{uname}] {content_text}'})

    # Add the current triggering message
    messages.append({
        'role': 'user',
        'content': f'[{incoming["username"]}] {incoming["content"]}'
    })
    return messages


# ──────────────────────────────────────────────
# Response Generator
# ──────────────────────────────────────────────

def generate_response(bot: dict, chat_history: list, incoming: dict,
                       api_key: str, base_url: str, model: str):
    """
    Returns (response_text, error_code | None)
    error_code: None = success, 'rate_limit', 'auth_error', 'timeout', str = other
    """
    try:
        client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=20)
        system_prompt = build_system_prompt(bot)
        ctx = build_context_messages(chat_history, incoming, bot['name'])

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
