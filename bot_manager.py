"""
bot_manager.py — Bot cooldown, günlük sayaç, Kick'e mesaj gönderme
"""
import threading
import time
import logging
import random
from datetime import date

import storage
from kick_client import send_kick_message

logger = logging.getLogger(__name__)


class BotManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._cooldowns: dict[int, float] = {}   # bot_id -> unix timestamp when cooldown ends
        self._daily_count: dict[int, int] = {}   # bot_id -> messages sent today
        self._daily_date = date.today()

    # ──────────────────────────────────────────
    # Cooldown
    # ──────────────────────────────────────────

    def _reset_daily_if_needed(self):
        today = date.today()
        if today != self._daily_date:
            with self._lock:
                self._daily_count.clear()
                self._daily_date = today

    def get_cooldown_remaining(self, bot_id: int) -> float:
        with self._lock:
            end = self._cooldowns.get(bot_id, 0)
            return max(0.0, end - time.time())

    def is_on_cooldown(self, bot_id: int) -> bool:
        return self.get_cooldown_remaining(bot_id) > 0

    def _set_cooldown(self, bot_id: int, seconds: float):
        with self._lock:
            self._cooldowns[bot_id] = time.time() + seconds

    # ──────────────────────────────────────────
    # Daily counter
    # ──────────────────────────────────────────

    def get_daily_count(self, bot_id: int) -> int:
        self._reset_daily_if_needed()
        with self._lock:
            return self._daily_count.get(bot_id, 0)

    def reset_daily_count(self, bot_id: int | None = None):
        with self._lock:
            if bot_id is not None:
                self._daily_count[bot_id] = 0
            else:
                self._daily_count.clear()

    def _increment_daily(self, bot_id: int):
        with self._lock:
            self._daily_count[bot_id] = self._daily_count.get(bot_id, 0) + 1

    # ──────────────────────────────────────────
    # Stats snapshot
    # ──────────────────────────────────────────

    def get_all_stats(self) -> list:
        self._reset_daily_if_needed()
        bots = storage.get_bots()
        result = []
        for bot in bots:
            result.append({
                'id': bot['id'],
                'name': bot['name'],
                'enabled': bool(bot['enabled']),
                'cooldown_remaining': round(self.get_cooldown_remaining(bot['id']), 1),
                'daily_count': self.get_daily_count(bot['id']),
                'daily_limit': bot['daily_limit'],
            })
        return result

    # ──────────────────────────────────────────
    # Sending
    # ──────────────────────────────────────────

    def send_message(self, bot: dict, chatroom_id, content: str):
        """
        Send a message from a bot character to Kick chat.
        Returns (success: bool, detail: str)
        """
        kick_account_id = bot.get('kick_account_id')
        if not kick_account_id:
            return False, 'Bot için Kick hesabı atanmamış'

        token = storage.get_kick_token_raw(kick_account_id)
        if not token:
            return False, 'Kick token bulunamadı'

        success, resp = send_kick_message(chatroom_id, content, token)

        if success:
            delay = random.randint(
                bot.get('min_delay', 8),
                bot.get('max_delay', 45)
            )
            self._set_cooldown(bot['id'], delay)
            self._increment_daily(bot['id'])
            logger.info(f'[{bot["name"]}] → "{content[:40]}"  (cooldown {delay}s)')
        else:
            logger.warning(f'[{bot["name"]}] send failed: {resp[:80]}')

        return success, resp

    def send_manual_message(self, kick_account_id: int, chatroom_id, content: str):
        """Send a message from any Kick account (manual override)."""
        token = storage.get_kick_token_raw(kick_account_id)
        if not token:
            return False, 'Kick token bulunamadı'
        return send_kick_message(chatroom_id, content, token)
