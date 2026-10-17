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

    def _get_fallback_account(self, exclude_id=None):
        """Finds the best available Kick account that has a Sanctum token."""
        try:
            accounts = storage.get_kick_accounts()
            # Shuffle accounts for dynamic pool distribution
            cand_accounts = [a for a in accounts if a.get('id') != exclude_id]
            random.shuffle(cand_accounts)
            for acc in cand_accounts:
                aid = acc['id']
                raw = storage.get_kick_token_raw(aid)
                if raw and not raw.startswith('eyJ') and '|' in raw:
                    return aid, raw
        except Exception as e:
            logger.warning(f'_get_fallback_account error: {e}')
        return None, None

    def get_pool_account(self):
        """Randomly pick an active account from pool for anonymous/broadcast chatting."""
        aid, raw = self._get_fallback_account()
        if aid:
            acc = next((a for a in storage.get_kick_accounts() if a['id'] == aid), None)
            uname = acc.get('username') if acc else f'Account_{aid}'
            return {
                'id': 9999,
                'name': uname,
                'kick_account_id': aid,
                'min_delay': 2,
                'max_delay': 5,
            }
        return {'id': 1, 'name': 'KickBot', 'kick_account_id': None}

    def send_message(self, bot: dict, chatroom_id, content: str):
        """
        Send a message from a bot character to Kick chat with account pool rotation.
        Returns (success: bool, detail: str)
        """
        kick_account_id = bot.get('kick_account_id')
        token = storage.get_kick_token_raw(kick_account_id) if kick_account_id else None

        # Auto-pool rotation: If configured or token invalid, grab from pool
        if not token or token.startswith('eyJ'):
            fb_id, fb_token = self._get_fallback_account(exclude_id=kick_account_id)
            if fb_token:
                kick_account_id = fb_id
                token = fb_token

        if not token:
            return False, 'Bot için geçerli bir Kick Bearer token bulunamadı'

        success, resp = send_kick_message(chatroom_id, content, token)

        # If 401 unauthenticated, try a backup account from pool
        if not success and 'User is not authenticated' in str(resp):
            logger.warning(f"Kick account #{kick_account_id} expired/unauthenticated, trying backup pool...")
            for _ in range(3):
                fb_id, fb_token = self._get_fallback_account(exclude_id=kick_account_id)
                if fb_token:
                    alt_ok, alt_resp = send_kick_message(chatroom_id, content, fb_token)
                    if alt_ok:
                        success, resp = alt_ok, alt_resp
                        kick_account_id = fb_id
                        break

        if success:
            delay = random.randint(
                bot.get('min_delay', 6),
                bot.get('max_delay', 35)
            )
            self._set_cooldown(bot['id'], delay)
            self._increment_daily(bot['id'])
            logger.info(f'[{bot["name"]}] → "{content[:40]}"  (cooldown {delay}s)')
        else:
            logger.warning(f'[{bot["name"]}] send failed: {resp[:80]}')

        return success, resp

    def trigger_hype(self, chatroom_id: int, count: int = 10, custom_content: str = None) -> list:
        """
        Send rapid hype emotes or text using separate accounts from the pool.
        """
        emotes = storage.get_emotes()
        results = []
        accounts = storage.get_kick_accounts()
        random.shuffle(accounts)

        sent = 0
        for acc in accounts:
            if sent >= count:
                break
            aid = acc['id']
            token = storage.get_kick_token_raw(aid)
            if not token or token.startswith('eyJ') or '|' not in token:
                continue

            content = custom_content if custom_content else random.choice(emotes)
            ok, resp = send_kick_message(chatroom_id, content, token)
            results.append({'account_id': aid, 'username': acc['username'], 'content': content, 'success': ok})
            if ok:
                sent += 1
            time.sleep(random.uniform(0.3, 0.8))

        return results

    def send_manual_message(self, kick_account_id: int, chatroom_id, content: str):
        """Send a message from any Kick account (manual override)."""
        token = None
        if not kick_account_id or kick_account_id == 0:
            kick_account_id, token = self._get_fallback_account()
        else:
            token = storage.get_kick_token_raw(kick_account_id)
            if token and token.startswith('eyJ'):
                return False, 'Bu hesapta Bearer token yerine web session cookie var. Lütfen geçerli bir Bearer token ekleyin.'

        if not token:
            # Fallback to any valid account
            kick_account_id, token = self._get_fallback_account()

        if not token:
            return False, 'Sistemde kayıtlı geçerli bir Kick Bearer token bulunamadı'

        success, resp = send_kick_message(chatroom_id, content, token)
        
        # If auto mode and failed, try another fallback
        if not success and (not kick_account_id or kick_account_id == 0) and 'User is not authenticated' in str(resp):
            fb_id, fb_token = self._get_fallback_account(exclude_id=kick_account_id)
            if fb_token:
                success, resp = send_kick_message(chatroom_id, content, fb_token)

        return success, resp
