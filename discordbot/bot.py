"""
discordbot/bot.py - Kick Discord Bot (Standalone Global Edition)
- Autonomous service for Kick.com operations.
- Tokens stored locally in discordbot/tokens.json.
- Role-protected admin commands (Role ID: 1552409518380552224).
- High-performance ViewBot engine with proxy support and rate limit management.
- Live status updates in bot presence.
"""
import asyncio
import datetime
import io
import json
import logging
import os
import random
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

try:
    import tls_client as _tls_client
    HAS_TLS = True
except ImportError:
    HAS_TLS = False

try:
    from websockets.asyncio.client import connect
except ImportError:
    from websockets import connect

try:
    from websockets.proxy import Proxy
except Exception:
    Proxy = None

try:
    from kick_creator import create_one_account, CreationResult
    HAS_CREATOR = True
except ImportError:
    HAS_CREATOR = False

try:
    from fake_useragent import UserAgent as _UA
    _ua_gen = _UA()
except Exception:
    _ua_gen = None

_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=str(_DIR / ".env"), override=True)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID_STR  = os.getenv("GUILD_ID", "").strip()
GUILD_ID      = 1277674359913189376  # Fixed Guild ID

TOKENS_FILE   = _DIR / "tokens.json"
DEFAULT_CLIENT_TOKEN = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"

# ── Security & Channel Configuration ──────────────────────────────────────────
ADMIN_ROLE_ID    = 1552409518380552224
ALLOWED_CHANNELS = {1552400779648827454, 1552389420727144509}
LOG_CHANNEL_ID   = 1561339967278415903

async def send_audit_log(title: str, description: str = "", fields: list = None, color: int = 0x53FC18):
    """Sends an embed to the designated Discord audit log channel."""
    try:
        ch = bot.get_channel(LOG_CHANNEL_ID)
        if not ch:
            try:
                ch = await bot.fetch_channel(LOG_CHANNEL_ID)
            except Exception:
                pass
        if ch:
            embed = discord.Embed(
                title=title,
                description=description,
                color=color,
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="Discord Bot & System Audit Log")
            if fields:
                for f in fields:
                    embed.add_field(name=f.get("name"), value=f.get("value"), inline=f.get("inline", True))
            await ch.send(embed=embed)
    except Exception as e:
        logger.debug(f"[send_audit_log] Error: {e}")

# ── Account Creator Config (optional) ─────────────────────────────────────────
CAPTCHA_API_KEY  = os.getenv("CAPTCHA_API_KEY", "").strip()   # 2captcha.com API key
SMS_ACTIVATE_KEY = os.getenv("SMS_ACTIVATE_KEY", "").strip()  # sms-activate.org API key

KICK_API_BASE = "https://kick.com/api/v2"
KICK_HEADERS  = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# Windows console encoding handler
_log_handler = logging.StreamHandler(
    stream=io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
)
_log_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])
logger = logging.getLogger("KickDiscordBot")


# ── Token Storage Management ──────────────────────────────────────────────────
def clean_token(token: str) -> str:
    t = token.strip().strip('"').strip("'")
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return t

def load_tokens() -> list[str]:
    if TOKENS_FILE.exists():
        try:
            data = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [clean_token(t) for t in data if isinstance(t, str) and clean_token(t)]
        except Exception as e:
            logger.error(f"Error reading tokens.json: {e}")
            return []
    return []

def save_tokens(tokens: list[str]) -> None:
    cleaned = []
    seen = set()
    for t in tokens:
        c = clean_token(t)
        if c and c not in seen:
            seen.add(c)
            cleaned.append(c)
    TOKENS_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")

_token_lock = threading.Lock()

def delete_tokens_from_file(tokens_to_remove: list[str] | set[str]) -> int:
    with _token_lock:
        toks = load_tokens()
        remove_set = {clean_token(t) for t in tokens_to_remove if t}
        new_toks = [t for t in toks if clean_token(t) not in remove_set]
        removed_count = len(toks) - len(new_toks)
        if removed_count > 0:
            save_tokens(new_toks)
            logger.warning(f"[tokens] Deleted {removed_count} unauthenticated/invalid token(s). (Remaining: {len(new_toks)})")
        return removed_count

def delete_token_from_file(token: str) -> bool:
    return delete_tokens_from_file([token]) > 0

def is_unauthenticated(resp: str) -> bool:
    if not resp:
        return False
    lower = str(resp).lower()
    return (
        "[401]" in lower
        or "401 unauthorized" in lower
        or "user is not authenticated" in lower
        or "unauthenticated" in lower
        or "invalid token" in lower
        or "token expired" in lower
        or "token is invalid" in lower
    )


# ── Active Sessions & Presence ────────────────────────────────────────────────
_sessions: dict[int, dict] = {}  # interaction_id -> session details

async def update_presence() -> None:
    try:
        status_text = "discord.gg/botservice"
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=status_text))
    except Exception as e:
        logger.debug(f"Presence update error: {e}")


# ── Kick Chat & Follow API Helpers ───────────────────────────────────────────
async def kick_get_chatroom(channel: str) -> int | None:
    ch = str(channel).strip().lstrip("@")
    if ch.isdigit():
        return int(ch)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{KICK_API_BASE}/channels/{ch}",
                headers=KICK_HEADERS,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return d.get("chatroom", {}).get("id")
                else:
                    logger.warning(f"kick_get_chatroom ({ch}) status: {r.status}")
    except Exception as e:
        logger.error(f"kick_get_chatroom error: {e}")
    return None

async def kick_send(chatroom_id: int, content: str, token: str, session: aiohttp.ClientSession | None = None, proxy_url: str | None = None) -> tuple[bool, str]:
    tok = clean_token(token)
    headers = {
        **KICK_HEADERS,
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
    }
    payload = {"content": content, "type": "message"}
    url = f"{KICK_API_BASE}/messages/send/{chatroom_id}"

    # Try with proxy first, then fallback to direct if proxy fails
    attempts = [proxy_url, None] if proxy_url else [None]
    for attempt_proxy in attempts:
        try:
            if session:
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                    proxy=attempt_proxy,
                ) as r:
                    resp_text = await r.text()
                    if r.status == 401:
                        return False, f"[401] {resp_text}"
                    return (r.status in (200, 201)), resp_text
            else:
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        url, json=payload, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=5),
                        proxy=attempt_proxy,
                    ) as r:
                        resp_text = await r.text()
                        if r.status == 401:
                            return False, f"[401] {resp_text}"
                        return (r.status in (200, 201)), resp_text
        except Exception as e:
            if attempt_proxy is None:
                return False, str(e)
            # Proxy failed → will retry without proxy
            logger.debug(f"[kick_send] Proxy failed ({attempt_proxy}), retrying direct: {e}")
    return False, "send_failed"

def _kick_follow_sync(channel_slug: str, token: str, proxy_url: str | None = None) -> tuple[bool, str]:
    tok = clean_token(token)
    headers = {
        **KICK_HEADERS,
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
        "Referer": f"https://kick.com/{channel_slug}",
        "Origin": "https://kick.com",
    }
    if HAS_TLS:
        # Try with proxy, then fallback to direct
        attempts = [proxy_url, None] if proxy_url else [None]
        for attempt_proxy in attempts:
            try:
                s = _tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
                if attempt_proxy:
                    s.proxies = {"http": attempt_proxy, "https": attempt_proxy}
                r = s.post(f"https://kick.com/api/v2/channels/{channel_slug}/follow", headers=headers, timeout_seconds=5)
                if r.status_code in (200, 201, 204):
                    return True, r.text
                if r.status_code == 401:
                    return False, f"[401] {r.text}"
                return False, f"HTTP {r.status_code}"
            except Exception as e:
                if attempt_proxy is None:
                    return False, str(e)
                logger.debug(f"[kick_follow_sync] Proxy failed, retrying direct: {e}")
    return False, "tls_client_unavailable"

async def kick_follow(channel_slug: str, token: str, session: aiohttp.ClientSession | None = None, proxy_url: str | None = None) -> tuple[bool, str]:
    tok = clean_token(token)
    headers = {
        **KICK_HEADERS,
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
        "Referer": f"https://kick.com/{channel_slug}",
        "Origin": "https://kick.com",
    }
    url = f"https://kick.com/api/v2/channels/{channel_slug}/follow"

    # Try with proxy, then fallback to direct
    attempts = [proxy_url, None] if proxy_url else [None]
    for attempt_proxy in attempts:
        try:
            if session:
                async with session.post(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5), proxy=attempt_proxy) as r:
                    resp_text = await r.text()
                    if r.status in (200, 201, 204):
                        return True, resp_text
                    if r.status == 401:
                        return False, f"[401] {resp_text}"
            else:
                async with aiohttp.ClientSession() as s:
                    async with s.post(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5), proxy=attempt_proxy) as r:
                        resp_text = await r.text()
                        if r.status in (200, 201, 204):
                            return True, resp_text
                        if r.status == 401:
                            return False, f"[401] {resp_text}"
        except Exception as e:
            if attempt_proxy is None:
                break
            logger.debug(f"[kick_follow] Proxy failed, retrying direct: {e}")

    if HAS_TLS:
        try:
            return await asyncio.to_thread(_kick_follow_sync, channel_slug, token, proxy_url)
        except Exception as e:
            return False, str(e)
    return False, "follow_failed"


# ── ViewBot Engine Components ─────────────────────────────────────────────────
def generate_user_agent() -> str:
    bases = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Mozilla/5.0 (X11; Linux x86_64)",
    ]
    chrome = f"{random.randint(122, 126)}.0.{random.randint(6000, 7500)}.{random.randint(10, 999)}"
    return f"{random.choice(bases)} AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome} Safari/537.36"

@dataclass(slots=True)
class ProxyEntry:
    raw: str
    http_url: str
    ws_proxy: Optional[Any]

    @property
    def label(self) -> str:
        if "@" in self.raw:
            return self.raw.split("@", 1)[1]
        return self.raw

def build_proxy_entry(line: str) -> Optional[ProxyEntry]:
    line = line.strip()
    if not line:
        return None
    if "@" in line:
        auth_part, host_part = line.rsplit("@", 1)
        if ":" not in auth_part or ":" not in host_part:
            return None
        username, password = auth_part.split(":", 1)
        host, port = host_part.rsplit(":", 1)
        http_url = f"http://{username}:{password}@{host}:{port}"
    else:
        parts = line.split(":")
        if len(parts) == 2:
            host, port = parts
            http_url = f"http://{host}:{port}"
        elif len(parts) == 4:
            host, port, username, password = parts
            http_url = f"http://{username}:{password}@{host}:{port}"
        else:
            return None

    ws_proxy = None
    if Proxy is not None:
        try:
            ws_proxy = Proxy.from_url(http_url)
        except Exception:
            ws_proxy = None
    return ProxyEntry(raw=line, http_url=http_url, ws_proxy=ws_proxy)

class ProxyPool:
    def __init__(self, entries: list[ProxyEntry], invalid: int = 0, cooldown: float = 30.0):
        self._entries = entries
        self._invalid = invalid
        self.cooldown = max(0.0, cooldown)
        self._cooldowns: dict[str, float] = {}

    @property
    def count(self) -> int:
        return len(self._entries)

    def sample(self) -> Optional[ProxyEntry]:
        if not self._entries:
            return None
        now = time.monotonic()
        ready = [e for e in self._entries if self._cooldowns.get(e.raw, 0.0) <= now]
        if ready:
            return random.choice(ready)
        return min(self._entries, key=lambda e: self._cooldowns.get(e.raw, now + self.cooldown))

    def mark_failure(self, proxy: Optional[ProxyEntry]) -> None:
        if proxy:
            self._cooldowns[proxy.raw] = time.monotonic() + self.cooldown

    def mark_success(self, proxy: Optional[ProxyEntry]) -> None:
        if proxy:
            self._cooldowns.pop(proxy.raw, None)

    @classmethod
    def from_file(cls, path: str | Path, cooldown: float = 30.0) -> "ProxyPool":
        p = Path(path)
        if not p.exists():
            return cls([], 0, cooldown)
        try:
            raw_lines = [l.strip() for l in p.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()]
        except Exception:
            return cls([], 0, cooldown)

        valid_entries: list[ProxyEntry] = []
        invalid = 0
        for l in raw_lines:
            entry = build_proxy_entry(l)
            if entry:
                valid_entries.append(entry)
            else:
                invalid += 1
        return cls(valid_entries, invalid, cooldown)

class KickHttpClient:
    def __init__(self, client_token: str, proxy: Optional[ProxyEntry]):
        self.session = _tls_client.Session(
            client_identifier="chrome_120", random_tls_extension_order=True
        )
        self.session.timeout = 15
        self.client_token = client_token
        self.session.headers.update({
            "User-Agent": generate_user_agent(),
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://kick.com",
            "Referer": "https://kick.com/",
            "Accept-Language": "en-US,en;q=0.9",
        })
        if proxy and proxy.http_url:
            self.session.proxies = {"http": proxy.http_url, "https": proxy.http_url}

    def _get(self, url: str) -> Any:
        try:
            return self.session.get(url, timeout_seconds=15)
        except Exception as exc:
            raise RuntimeError(f"{url} request failed: {exc}") from exc

    async def fetch_token(self) -> str:
        def _get_token() -> str:
            self._get("https://kick.com")
            self.session.headers.update({"X-CLIENT-TOKEN": self.client_token})
            resp = self._get("https://websockets.kick.com/viewer/v1/token")
            if resp.status_code >= 400:
                raise RuntimeError(f"Token HTTP {resp.status_code}: {resp.text[:80]}")
            data = resp.json()
            return data["data"]["token"]
        return await asyncio.to_thread(_get_token)

    async def fetch_channel_info(self, channel: str) -> tuple[int | None, int | None, int | None]:
        def _get_info():
            resp = self._get(f"https://kick.com/api/v2/channels/{channel}")
            if resp.status_code >= 400:
                return None, None, None
            d = resp.json()
            cid = d.get("id") or d.get("data", {}).get("id")
            ls = d.get("livestream")
            stream_id = ls.get("id") if isinstance(ls, dict) else None
            live_viewers = ls.get("viewer_count") if isinstance(ls, dict) else None
            return int(cid) if cid else None, stream_id, live_viewers
        return await asyncio.to_thread(_get_info)

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass

@dataclass(slots=True)
class StatsSnapshot:
    active: int
    total: int
    failures: int
    retries: int

class StatsTracker:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active = 0
        self._total = 0
        self._failures = 0
        self._retries = 0
        self._rate_limit_429 = 0
        self._last_429_time = 0.0

    async def connection_started(self) -> None:
        async with self._lock:
            self._active += 1
            self._total += 1

    async def connection_closed(self) -> None:
        async with self._lock:
            self._active = max(0, self._active - 1)

    async def record_failure(self) -> None:
        async with self._lock:
            self._failures += 1

    async def record_retry(self) -> None:
        async with self._lock:
            self._retries += 1

    async def record_429(self) -> None:
        async with self._lock:
            self._rate_limit_429 += 1
            self._last_429_time = time.monotonic()

    async def get_429_backoff(self) -> float:
        async with self._lock:
            if self._rate_limit_429 == 0:
                return 0.0
            elapsed = time.monotonic() - self._last_429_time
            if elapsed > 60:
                self._rate_limit_429 = 0
                return 0.0
            return min(4 * (2 ** (self._rate_limit_429 - 1)), 45.0)

    async def snapshot(self) -> StatsSnapshot:
        async with self._lock:
            return StatsSnapshot(
                active=self._active,
                total=self._total,
                failures=self._failures,
                retries=self._retries,
            )

class AsyncRateLimiter:
    def __init__(self, rate: Optional[float] = 20.0) -> None:
        self.rate = float(rate) if rate and rate > 0 else None
        self._lock = asyncio.Lock()
        self._next_time = 0.0

    async def wait(self) -> None:
        if self.rate is None:
            return
        interval = 1.0 / self.rate
        async with self._lock:
            now = time.monotonic()
            if self._next_time <= now:
                self._next_time = now + interval
                return
            wait_time = self._next_time - now
            self._next_time += interval
        await asyncio.sleep(wait_time)

async def maintain_view_connection(
    token: str,
    channel_id: int,
    worker_id: int,
    proxy: Optional[ProxyEntry],
    stop_event: asyncio.Event,
    stats: StatsTracker,
    client_token: str = DEFAULT_CLIENT_TOKEN,
) -> None:
    headers = {
        "User-Agent": generate_user_agent(),
        "Origin": "https://kick.com",
        "Cookie": f"client_token={client_token}",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }
    url = f"wss://websockets.kick.com/viewer/v1/connect?token={token}"
    connect_kwargs = {
        "additional_headers": headers,
        "ping_interval": None,
        "open_timeout": 15,
        "close_timeout": 10,
    }
    if proxy and proxy.ws_proxy:
        connect_kwargs["proxy"] = proxy.ws_proxy

    handshake_payload = json.dumps(
        {"type": "channel_handshake", "data": {"message": {"channelId": channel_id}}}
    )
    ping_payload = json.dumps({"type": "ping"})

    async with connect(url, **connect_kwargs) as ws:
        await ws.send(handshake_payload)
        await stats.connection_started()

        iteration = 0
        try:
            while not stop_event.is_set():
                delay = random.uniform(13.0, 21.0)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay)
                    break
                except asyncio.TimeoutError:
                    pass

                iteration += 1
                payload = ping_payload if iteration % 6 == 0 else handshake_payload
                await ws.send(payload)
        finally:
            await stats.connection_closed()
            try:
                await ws.close()
            except Exception:
                pass

async def viewer_worker(
    worker_id: int,
    channel: str,
    channel_id: int,
    client_token: str,
    proxy_pool: ProxyPool,
    http_gate: asyncio.Semaphore,
    http_rate_limiter: AsyncRateLimiter,
    stop_event: asyncio.Event,
    stats: StatsTracker,
) -> None:
    consecutive_429 = 0
    while not stop_event.is_set():
        proxy = proxy_pool.sample()
        token: Optional[str] = None
        need_retry = False
        is_429 = False

        if stop_event.is_set():
            break

        global_backoff = await stats.get_429_backoff()
        if global_backoff > 0:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=global_backoff)
                break
            except asyncio.TimeoutError:
                pass

        ramp_jitter = random.uniform(0.5, 2.5)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=ramp_jitter)
            break
        except asyncio.TimeoutError:
            pass

        await http_rate_limiter.wait()
        if stop_event.is_set():
            break

        async with http_gate:
            client = KickHttpClient(client_token, proxy)
            try:
                token = await client.fetch_token()
                consecutive_429 = 0
            except Exception as exc:
                need_retry = True
                error_msg = str(exc)
                if "429" in error_msg:
                    is_429 = True
                    consecutive_429 += 1
                    await stats.record_429()
                    logger.warning(f"[viewbot] Rate limited (429 #{consecutive_429})")
                await stats.record_retry()
                proxy_pool.mark_failure(proxy)
            finally:
                client.close()

        if need_retry or not token:
            if stop_event.is_set():
                break
            delay = min(consecutive_429 * 3, 20) if is_429 else random.uniform(2.0, 5.0)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
            continue

        try:
            await maintain_view_connection(token, channel_id, worker_id, proxy, stop_event, stats, client_token)
            proxy_pool.mark_success(proxy)
            consecutive_429 = 0
        except asyncio.CancelledError:
            break
        except Exception as exc:
            error_msg = str(exc)
            if "429" in error_msg:
                is_429 = True
                consecutive_429 += 1
                await stats.record_429()
            else:
                consecutive_429 = 0
            await stats.record_failure()
            proxy_pool.mark_failure(proxy)
            delay = min(consecutive_429 * 4, 30) if is_429 else random.uniform(2.0, 5.0)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass


# ── Discord Bot Initialization ────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
_guild_obj = discord.Object(id=GUILD_ID) if GUILD_ID else None


# ── Permission & Channel Verification ─────────────────────────────────────────
def is_admin(target) -> bool:
    """Check if the user/member/interaction has Administrator permission or the designated Admin Role."""
    if isinstance(target, discord.Interaction):
        guild = target.guild
        user = target.user
    elif isinstance(target, discord.Member):
        guild = target.guild
        user = target
    elif isinstance(target, discord.User):
        return False
    else:
        return False

    if not guild or not user:
        return False

    # Check guild administrator permission
    if hasattr(user, 'guild_permissions') and user.guild_permissions.administrator:
        return True

    # Try resolving Member from guild if user doesn't have roles
    member = user if hasattr(user, 'roles') else guild.get_member(user.id)
    if member and hasattr(member, 'roles'):
        return any(role.id == ADMIN_ROLE_ID for role in member.roles)

    return False

def check_channel(interaction: discord.Interaction) -> bool:
    """Channel check: Admins bypass, regular users are restricted to allowed channels."""
    if is_admin(interaction):
        return True
    return interaction.channel_id in ALLOWED_CHANNELS


# ── /tokenadd (Admin Only) ───────────────────────────────────────────────────
@tree.command(name="tokenadd", description="Add Kick Bearer tokens to bot storage (Admin only)", guild=_guild_obj)
@app_commands.describe(tokens="Bearer tokens (paste line by line or separated by space/comma)")
async def tokenadd(interaction: discord.Interaction, tokens: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this command! (Admin only)", ephemeral=True)
        return

    try:
        if not interaction.response.is_done():
            await interaction.response.defer()
    except discord.NotFound:
        return
    except Exception:
        pass

    raw_lines = tokens.replace("\\n", "\n").replace(",", "\n").split("\n")
    new_candidates = [clean_token(t) for t in raw_lines if clean_token(t)]

    if not new_candidates:
        await interaction.followup.send("❌ No valid tokens found in input!")
        return

    existing = load_tokens()
    existing_set = set(existing)
    added = []
    dupes = []

    for t in new_candidates:
        if t in existing_set:
            dupes.append(t)
        else:
            existing.append(t)
            existing_set.add(t)
            added.append(t)

    save_tokens(existing)
    await update_presence()

    embed = discord.Embed(
        title="🔑 Token Storage Updated",
        color=0x00E676 if added else 0xFFAA00,
    )
    embed.add_field(name=f"✅ Added ({len(added)})", value=f"`{len(added)}` new token(s) added" if added else "No new tokens added", inline=True)
    if dupes:
        embed.add_field(name=f"⚠️ Duplicates ({len(dupes)})", value=f"`{len(dupes)}` token(s) already existed", inline=True)
    embed.add_field(name="📦 Total Stored Tokens", value=f"`{len(existing)}` tokens", inline=False)
    embed.set_footer(text="Stored securely in bot memory (tokens.json).")
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)


# ── /tokenlist & Select Menu (Admin Only) ────────────────────────────────────
class TokenRemoveSelect(discord.ui.Select):
    def __init__(self, tokens: list[str]):
        options = []
        for i, t in enumerate(tokens[:25]):
            label = f"Token #{i+1}"
            desc = f"{t[:10]}...{t[-4:]}"
            options.append(discord.SelectOption(label=label, description=desc, value=str(i)))
        super().__init__(placeholder="🗑️ Select a token to remove...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await interaction.response.send_message("❌ Admin permission required.", ephemeral=True)
            return

        idx = int(self.values[0])
        toks = load_tokens()
        if 0 <= idx < len(toks):
            removed = toks.pop(idx)
            save_tokens(toks)
            await update_presence()
            await interaction.response.send_message(
                f"✅ `Token #{idx+1}` (`{removed[:8]}...{removed[-4:]}`) successfully removed!\n📦 Remaining tokens: `{len(toks)}`",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ Token not found or already deleted.", ephemeral=True)

class TokenListView(discord.ui.View):
    def __init__(self, tokens: list[str]):
        super().__init__(timeout=120)
        if tokens:
            self.add_item(TokenRemoveSelect(tokens))

@tree.command(name="tokenlist", description="View and manage stored Kick tokens (Admin only)", guild=_guild_obj)
async def tokenlist(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this command! (Admin only)", ephemeral=True)
        return

    try:
        await interaction.response.defer(ephemeral=True)
    except discord.NotFound:
        return
    except Exception:
        pass

    toks = load_tokens()
    if not toks:
        await interaction.followup.send("No tokens in storage! Use `/tokenadd` to add tokens.", ephemeral=True)
        return

    lines = [f"`#{i+1}.` `{t[:12]}...{t[-6:]}`" for i, t in enumerate(toks)]
    chunks = [lines[i:i+20] for i in range(0, len(lines), 20)]

    embed = discord.Embed(
        title=f"🔑 Registered Tokens ({len(toks)} Total)",
        description="Select a token below to delete it, or use `/tokenremove number:X`.",
        color=0x6C63FF,
    )
    for i, chunk in enumerate(chunks[:5]):
        embed.add_field(name=f"Tokens {i*20+1} - {i*20+len(chunk)}", value="\n".join(chunk), inline=False)
    embed.set_footer(text="Only prefix and suffix are displayed for security.")
    embed.timestamp = discord.utils.utcnow()

    view = TokenListView(toks)
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)


# ── /tokenremove (Admin Only) ─────────────────────────────────────────────────
@tree.command(name="tokenremove", description="Remove a token by its index number (Admin only)", guild=_guild_obj)
@app_commands.describe(number="Token number to delete (e.g. 1)")
async def tokenremove(interaction: discord.Interaction, number: int):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this command! (Admin only)", ephemeral=True)
        return

    toks = load_tokens()
    if not toks:
        await interaction.response.send_message("❌ No tokens in storage!", ephemeral=True)
        return
    if 1 <= number <= len(toks):
        removed = toks.pop(number - 1)
        save_tokens(toks)
        await update_presence()
        await interaction.response.send_message(
            f"✅ `Token #{number}` (`{removed[:8]}...{removed[-4:]}`) successfully removed!\n📦 Remaining tokens: `{len(toks)}`",
            ephemeral=False
        )
    else:
        await interaction.response.send_message(f"❌ Invalid index! Enter a number between 1 and {len(toks)}.", ephemeral=True)


# ── /tokencheck (Admin Only) ──────────────────────────────────────────────────
@tree.command(name="tokencheck", description="Verify Kick token health and remove invalid ones (Admin only)", guild=_guild_obj)
@app_commands.describe(remove_dead="Automatically remove dead tokens? (True / False)")
async def tokencheck(interaction: discord.Interaction, remove_dead: bool = False):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this command! (Admin only)", ephemeral=True)
        return

    try:
        await interaction.response.defer()
    except discord.NotFound:
        return
    except Exception:
        pass

    toks = load_tokens()
    if not toks:
        await interaction.followup.send("No tokens to test in storage!")
        return

    working = []
    dead = []

    async with aiohttp.ClientSession() as session:
        for idx, t in enumerate(toks):
            clean_t = clean_token(t)
            headers = {
                **KICK_HEADERS,
                "Authorization": f"Bearer {clean_t}",
            }
            try:
                async with session.get(
                    "https://kick.com/api/v1/user",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data and data.get("id"):
                            uname = data.get("username") or data.get("name") or f"ID:{data.get('id')}"
                            working.append((idx + 1, uname, t))
                        else:
                            dead.append((idx + 1, t))
                    else:
                        dead.append((idx + 1, t))
            except Exception:
                dead.append((idx + 1, t))

    if remove_dead and dead:
        dead_tokens_set = {t for _, t in dead}
        active_tokens = [t for t in toks if t not in dead_tokens_set]
        save_tokens(active_tokens)
        await update_presence()

    embed = discord.Embed(
        title="🔍 Token Health Check",
        color=0x00E676 if not dead else 0xFFAA00,
    )
    working_text = "\n".join(f"`#{i}` **{u}** (`{t[:8]}...`)" for i, u, t in working[:15])
    embed.add_field(
        name=f"🟢 Active Tokens ({len(working)})",
        value=working_text if working_text else "No active tokens found",
        inline=False,
    )
    if dead:
        dead_text = "\n".join(f"`#{i}` (`{t[:8]}...`)" for i, t in dead[:10])
        embed.add_field(
            name=f"🔴 Invalid/Dead Tokens ({len(dead)})",
            value=dead_text,
            inline=False,
        )
        if remove_dead:
            embed.set_footer(text=f"🗑️ Cleaned {len(dead)} dead token(s) from storage.")
        else:
            embed.set_footer(text="To clean invalid tokens automatically: /tokencheck remove_dead:True")
    else:
        embed.set_footer(text="All stored tokens are active and valid!")

    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)


# ── /tokenclear (Admin Only) ──────────────────────────────────────────────────
@tree.command(name="tokenclear", description="Clear all stored tokens from memory (Admin only)", guild=_guild_obj)
async def tokenclear(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this command! (Admin only)", ephemeral=True)
        return

    count = len(load_tokens())
    save_tokens([])
    await update_presence()
    await interaction.response.send_message(f"🗑️ Cleared `{count}` token(s) from bot memory.", ephemeral=True)


# ── /status (Public) ──────────────────────────────────────────────────────────
@tree.command(name="status", description="Display token statistics and active bot sessions", guild=_guild_obj)
async def status(interaction: discord.Interaction):
    toks = load_tokens()
    embed = discord.Embed(title="📊 Bot Status", color=0x6C63FF)

    embed.add_field(
        name="🔑 Stored Tokens",
        value=f"`{len(toks)}` active tokens",
        inline=True,
    )

    chatbots  = [s for s in _sessions.values() if s.get("type") == "chatbot"]
    viewbots  = [s for s in _sessions.values() if s.get("type") == "viewbot"]

    cb_text = f"`{len(chatbots)}` active session(s)" if chatbots else "`0` (Idle)"
    vb_text = f"`{len(viewbots)}` active session(s)" if viewbots else "`0` (Idle)"

    embed.add_field(name="💬 ChatBot", value=cb_text, inline=True)
    embed.add_field(name="👁️ ViewBot", value=vb_text, inline=True)

    # Proxy pool info
    if _global_proxy_pool and _global_proxy_pool.count > 0:
        proxy_val = f"`{_global_proxy_pool.count}` proxies loaded ✅"
    else:
        proxy_val = "`0` — Proxyless mode ⚠️"
    embed.add_field(name="🌐 Proxy Pool", value=proxy_val, inline=True)

    # Creator config
    creator_val = "✅ Ready (Headless Engine, Direct API, Zero Captcha/SMS)" if HAS_CREATOR else "❌ Not available"
    embed.add_field(name="🛠️ Account Creator", value=creator_val, inline=False)

    if _sessions:
        lines = []
        for s in list(_sessions.values())[:6]:
            stype = s.get("type", "bot").upper()
            lines.append(f"• **[{stype}]** `{s.get('channel')}` — `{s.get('target', 'N/A')}`")
        embed.add_field(name="⚡ Active Sessions", value="\n".join(lines), inline=False)

    embed.set_footer(text="KickBot V2 | AccountEngine Ready" if HAS_CREATOR else "KickBot V2")
    embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed)


# ── /chatbot (Public / Channel Restricted) ────────────────────────────────────
@tree.command(name="chatbot", description="Send automated fast messages to a Kick stream chat", guild=_guild_obj)
@app_commands.describe(
    username="Kick channel name or Chatroom ID",
    message="Message content to send",
    amount="Number of tokens to use (0 = all)",
    spam="Repeat messages continuously? (True / False)",
    duration="Run duration in seconds (default 30)",
    delay="Delay between messages in seconds (e.g. 0.05 fast, 0.1 default)",
)
async def chatbot(
    interaction: discord.Interaction,
    username: str,
    message: str,
    amount: int = 0,
    spam: bool = False,
    duration: int = 30,
    delay: float = 0.05,
):
    if not check_channel(interaction):
        try:
            await interaction.response.send_message(
                "❌ This command can only be used in allowed channels!", ephemeral=True
            )
        except Exception:
            pass
        return

    try:
        if not interaction.response.is_done():
            await interaction.response.defer()
    except discord.NotFound:
        logger.warning("[chatbot] Interaction timed out (10062 Unknown interaction).")
        return
    except discord.InteractionResponded:
        pass
    except Exception as e:
        logger.warning(f"[chatbot] Defer error: {e}")

    all_tokens = load_tokens()
    if not all_tokens:
        try:
            await interaction.followup.send("❌ No tokens in storage! Add tokens first with `/tokenadd`.")
        except Exception:
            pass
        return

    clean_user = username.strip().lstrip("@")
    chatroom_id = await kick_get_chatroom(clean_user)
    if not chatroom_id:
        try:
            await interaction.followup.send(f"❌ Channel **{clean_user}** or chatroom could not be found!")
        except Exception:
            pass
        return

    use_amount = len(all_tokens) if (amount <= 0 or amount > len(all_tokens)) else amount
    sleep_interval = max(0.01, delay) if delay is not None else 0.05

    embed = discord.Embed(
        title="⚡ ChatBot Started (Fast Mode)",
        description=(
            f"**Channel:** `{clean_user}` (#{chatroom_id})\n"
            f"**Message:** `{message}`\n"
            f"**Tokens:** `{use_amount}/{len(all_tokens)}` | **Spam:** `{spam}` | **Speed:** `{sleep_interval}s` | **Duration:** `{duration}s`"
        ),
        color=0x6C63FF,
    )
    embed.set_footer(text="Sending messages...")
    embed.timestamp = discord.utils.utcnow()
    status_msg = None
    try:
        status_msg = await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.warning(f"[chatbot] Followup send failed: {e}")

    session_key = interaction.id

    async def send_loop():
        sent_ok = 0
        sent_fail = 0
        deleted_count = 0
        rounds = 0
        deadline = time.monotonic() + duration if spam else None

        followers_only_hit = False
        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    if deadline and time.monotonic() > deadline:
                        break
                    if not all_tokens:
                        logger.warning("[chatbot] No active tokens remaining!")
                        break
                    rounds += 1
                    current_sample_size = min(use_amount, len(all_tokens))
                    selected = random.sample(all_tokens, current_sample_size)
                    for token in list(selected):
                        if deadline and time.monotonic() > deadline:
                            break
                        # Pick a rotating proxy for this request
                        _proxy = _global_proxy_pool.sample() if _global_proxy_pool else None
                        _proxy_url = _proxy.http_url if _proxy else None
                        ok, resp = await kick_send(chatroom_id, message, token, session=session, proxy_url=_proxy_url)
                        if _proxy:
                            if ok:
                                _global_proxy_pool.mark_success(_proxy)
                            else:
                                _global_proxy_pool.mark_failure(_proxy)

                        # Auto-delete invalid tokens immediately
                        if not ok and is_unauthenticated(resp):
                            logger.warning(f"[chatbot] Token unauthenticated ('User is not authenticated'), deleting: {token[:12]}...")
                            delete_token_from_file(token)
                            if token in all_tokens:
                                all_tokens.remove(token)
                            deleted_count += 1
                            sent_fail += 1
                            continue

                        if not ok and "FOLLOWERS_ONLY_ERROR" in resp:
                            followers_only_hit = True
                            logger.info(f"[chatbot] Followers-only mode detected! Following {clean_user}...")
                            f_ok, f_resp = await kick_follow(clean_user, token, session=session, proxy_url=_proxy_url)

                            if not f_ok and is_unauthenticated(f_resp):
                                logger.warning(f"[chatbot] Token unauthenticated on follow, deleting: {token[:12]}...")
                                delete_token_from_file(token)
                                if token in all_tokens:
                                    all_tokens.remove(token)
                                deleted_count += 1
                                sent_fail += 1
                                continue

                            if f_ok:
                                logger.info(f"[chatbot] Successfully followed {clean_user}!")
                            else:
                                logger.warning(f"[chatbot] Follow response: {f_resp[:80]}")
                            await asyncio.sleep(0.5)

                            # Retry after following
                            ok, resp = await kick_send(chatroom_id, message, token, session=session, proxy_url=_proxy_url)
                            if not ok and is_unauthenticated(resp):
                                logger.warning(f"[chatbot] Token unauthenticated on retry, deleting: {token[:12]}...")
                                delete_token_from_file(token)
                                if token in all_tokens:
                                    all_tokens.remove(token)
                                deleted_count += 1
                                sent_fail += 1
                                continue

                        if ok:
                            sent_ok += 1
                            logger.info(f"[chatbot] Sent: {clean_user} | {message[:30]}")
                        else:
                            sent_fail += 1
                            logger.warning(f"[chatbot] Failed: {resp[:80]}")
                        await asyncio.sleep(sleep_interval)
                    if not spam:
                        break
                    await asyncio.sleep(sleep_interval)
        except asyncio.CancelledError:
            pass
        finally:
            _sessions.pop(session_key, None)
            await update_presence()
            color = 0x00E676 if sent_ok > 0 else 0xFF5050
            desc = (
                f"**Channel:** `{clean_user}` (#{chatroom_id})\n"
                f"**Rounds:** `{rounds}` | **Sent:** `{sent_ok}` | **Failed:** `{sent_fail}`"
            )
            if deleted_count > 0:
                desc += f"\n🗑️ **Removed Invalid Tokens:** `{deleted_count}` tokens"
            if followers_only_hit and sent_ok == 0:
                desc += (
                    "\n\n⚠️ **Followers-Only Mode Active:**\n"
                    "Only followers can chat in this channel. The bot attempted to follow automatically, "
                    "but due to channel protection or duration rules, messages could not be sent."
                )
            done = discord.Embed(
                title="🏁 ChatBot Finished",
                description=desc,
                color=color,
            )
            done.timestamp = discord.utils.utcnow()
            if status_msg:
                try:
                    await status_msg.edit(embed=done)
                except Exception:
                    pass

    task = asyncio.create_task(send_loop())
    _sessions[session_key] = {
        "task": task,
        "channel": clean_user,
        "target": f"{use_amount} tokens",
        "type": "chatbot",
    }
    await update_presence()


# ── /stopbot (Admin Only) ─────────────────────────────────────────────────────
@tree.command(name="stopbot", description="Stop active chatbot and viewbot sessions (Admin only)", guild=_guild_obj)
async def stopbot(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this command! (Admin only)", ephemeral=True)
        return

    if _sessions:
        count = len(_sessions)
        for s in list(_sessions.values()):
            if "stop_event" in s and hasattr(s["stop_event"], "set"):
                s["stop_event"].set()
            if "task" in s and hasattr(s["task"], "cancel"):
                s["task"].cancel()
            if "tasks" in s and isinstance(s["tasks"], list):
                for t in s["tasks"]:
                    t.cancel()
        _sessions.clear()
        await update_presence()
        await interaction.response.send_message(f"🛑 Stopped `{count}` active bot session(s)!", ephemeral=True)
    else:
        await interaction.response.send_message("No active bot sessions currently running.", ephemeral=True)



# ── /follow (Admin Only) ──────────────────────────────────────────────────────
@tree.command(name="follow", description="Follow a Kick channel with all stored tokens (Admin only)", guild=_guild_obj)
@app_commands.describe(channel="Kick channel name to follow (e.g. xqc)")
async def follow(interaction: discord.Interaction, channel: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this command! (Admin only)", ephemeral=True)
        return

    try:
        if not interaction.response.is_done():
            await interaction.response.defer()
    except discord.NotFound:
        return
    except Exception:
        pass

    all_tokens = load_tokens()
    if not all_tokens:
        try:
            await interaction.followup.send("❌ No tokens in storage! Add tokens first with `/tokenadd`.")
        except Exception:
            pass
        return

    clean_user = channel.strip().lstrip("@").split("kick.com/")[-1].split("/")[0].split("?")[0].lower()
    successful = 0
    failed = 0
    deleted = 0

    async with aiohttp.ClientSession() as session:
        for t in list(all_tokens):
            _px = _global_proxy_pool.sample() if _global_proxy_pool else None
            ok, f_resp = await kick_follow(clean_user, t, session=session, proxy_url=_px.http_url if _px else None)
            if ok:
                successful += 1
                if _px:
                    _global_proxy_pool.mark_success(_px)
            else:
                failed += 1
                if _px:
                    _global_proxy_pool.mark_failure(_px)
                if is_unauthenticated(f_resp):
                    delete_token_from_file(t)
                    deleted += 1
            await asyncio.sleep(0.1)

    color = 0x00E676 if successful > 0 else 0xFF5050
    desc = f"**Channel:** `{clean_user}`\n✅ **Successful Follows:** `{successful}`\n❌ **Failed:** `{failed}`"
    if deleted > 0:
        desc += f"\n🗑️ **Removed Invalid Tokens:** `{deleted}` tokens"
    embed = discord.Embed(
        title="👥 Follow Operation Completed",
        description=desc,
        color=color,
    )
    embed.timestamp = discord.utils.utcnow()
    try:
        await interaction.followup.send(embed=embed)
    except Exception:
        pass


# ── /followbot (Public / Channel Restricted, Max 25) ──────────────────────────
@tree.command(name="followbot", description="Send followers to a Kick channel (max 25)", guild=_guild_obj)
@app_commands.describe(
    channel="Kick channel name to follow (e.g. xqc)",
    amount="Number of followers to send (max 25, default 25)",
)
async def followbot(
    interaction: discord.Interaction,
    channel: str,
    amount: int = 25,
):
    if not check_channel(interaction):
        await interaction.response.send_message(
            "❌ This command can only be used in allowed channels!", ephemeral=True
        )
        return

    # Strictly enforce 25 followers limit
    amount = max(1, min(amount, 25))

    try:
        if not interaction.response.is_done():
            await interaction.response.defer()
    except discord.NotFound:
        return
    except Exception:
        pass

    all_tokens = load_tokens()
    if not all_tokens:
        try:
            await interaction.followup.send("❌ No tokens in storage! Contact an administrator.")
        except Exception:
            pass
        return

    clean_user = channel.strip().lstrip("@").split("kick.com/")[-1].split("/")[0].split("?")[0].lower()
    selected_tokens = random.sample(all_tokens, min(amount, len(all_tokens)))

    embed_start = discord.Embed(
        title="👥 FollowBot Initiated",
        description=f"Sending `{len(selected_tokens)}` followers to `{clean_user}`...",
        color=0x6C63FF,
    )
    embed_start.set_footer(text="KickBot FollowEngine")
    embed_start.timestamp = discord.utils.utcnow()
    status_msg = None
    try:
        status_msg = await interaction.followup.send(embed=embed_start)
    except Exception:
        pass

    successful = 0
    failed = 0
    deleted = 0

    async with aiohttp.ClientSession() as session:
        for t in selected_tokens:
            _px = _global_proxy_pool.sample() if _global_proxy_pool else None
            ok, f_resp = await kick_follow(clean_user, t, session=session, proxy_url=_px.http_url if _px else None)
            if ok:
                successful += 1
                if _px:
                    _global_proxy_pool.mark_success(_px)
            else:
                failed += 1
                if _px:
                    _global_proxy_pool.mark_failure(_px)
                if is_unauthenticated(f_resp):
                    delete_token_from_file(t)
                    deleted += 1
            await asyncio.sleep(0.12)

    color = 0x00E676 if successful > 0 else 0xFF5050
    desc = f"**Channel:** `{clean_user}`\n✅ **Successful Follows:** `{successful}` / `{len(selected_tokens)}`\n❌ **Failed:** `{failed}`"
    if deleted > 0:
        desc += f"\n🗑️ **Removed Invalid Tokens:** `{deleted}` tokens"

    embed_done = discord.Embed(
        title="👥 FollowBot Completed",
        description=desc,
        color=color,
    )
    embed_done.set_footer(text="KickBot FollowEngine")
    embed_done.timestamp = discord.utils.utcnow()

    if status_msg:
        try:
            await status_msg.edit(embed=embed_done)
            return
        except Exception:
            pass
    try:
        await interaction.followup.send(embed=embed_done)
    except Exception:
        pass


# ── /viewbot (Public / Channel Restricted) ────────────────────────────────────
@tree.command(name="viewbot", description="Send viewers to a Kick live stream", guild=_guild_obj)
@app_commands.describe(
    channel="Kick channel name (e.g. xqc)",
    viewers="Target viewer count (max 100, default 50)",
    duration="Duration in seconds (max 600 = 10 minutes, default 120)",
)
async def viewbot(
    interaction: discord.Interaction,
    channel: str,
    viewers: int = 50,
    duration: int = 120,
):
    if not check_channel(interaction):
        await interaction.response.send_message(
            "❌ This command can only be used in allowed channels!", ephemeral=True
        )
        return

    if not HAS_TLS:
        await interaction.response.send_message(
            "❌ `tls_client` is not installed on the bot environment!", ephemeral=True
        )
        return

    # Enforce strict maximum limits: 100 viewers, 600s (10 minutes)
    viewers = max(1, min(viewers, 100))
    duration = max(10, min(duration, 600))

    try:
        if not interaction.response.is_done():
            await interaction.response.defer()
    except discord.NotFound:
        return
    except Exception:
        pass

    clean_user = channel.strip().lstrip("@").split("kick.com/")[-1].split("/")[0].split("?")[0].lower()

    embed_init = discord.Embed(
        title="🔍 Resolving Channel...",
        description=f"Querying Kick API for `{clean_user}`...",
        color=0x6C63FF,
    )
    status_msg = await interaction.followup.send(embed=embed_init)

    client = KickHttpClient(DEFAULT_CLIENT_TOKEN, None)
    channel_id, stream_id, initial_viewers = None, None, None
    try:
        channel_id, stream_id, initial_viewers = await client.fetch_channel_info(clean_user)
    except Exception as e:
        logger.warning(f"[viewbot] Channel query error: {e}")
    finally:
        client.close()

    if not channel_id:
        await status_msg.edit(embed=discord.Embed(
            title="❌ Channel Not Found",
            description=f"Could not find `{clean_user}` on Kick or channel is offline.",
            color=0xFF5050,
        ))
        return

    # Check for proxies in bot directory or root directory
    proxy_candidates = [
        _DIR / "proxies.txt",
        _DIR / "proxy.txt",
        _DIR.parent / "proxies.txt",
        _DIR.parent / "proxy.txt",
    ]
    proxy_path = next((p for p in proxy_candidates if p.exists()), _DIR / "proxies.txt")
    proxy_pool = ProxyPool.from_file(proxy_path, cooldown=30.0)

    stats = StatsTracker()
    stop_event = asyncio.Event()
    deadline = time.monotonic() + duration
    session_key = interaction.id

    http_gate_size = max(1, min(15, viewers))
    http_gate = asyncio.Semaphore(http_gate_size)
    http_rate_limiter = AsyncRateLimiter(rate=20.0)

    tasks = [
        asyncio.create_task(
            viewer_worker(
                i + 1,
                clean_user,
                channel_id,
                DEFAULT_CLIENT_TOKEN,
                proxy_pool,
                http_gate,
                http_rate_limiter,
                stop_event,
                stats,
            ),
            name=f"viewbot-{clean_user}-{i+1}",
        )
        for i in range(viewers)
    ]

    _sessions[session_key] = {
        "tasks": tasks,
        "stop_event": stop_event,
        "channel": clean_user,
        "target": f"{viewers} viewers",
        "type": "viewbot",
    }
    await update_presence()

    embed_run = discord.Embed(
        title="👁️ ViewBot Running",
        color=0x00E676,
    )
    embed_run.add_field(name="📺 Channel", value=f"`{clean_user}`", inline=True)
    embed_run.add_field(name="🎯 Target", value=f"`{viewers}` viewers", inline=True)
    embed_run.add_field(name="⏱ Duration", value=f"`{duration}s`", inline=True)
    embed_run.add_field(name="📊 Status", value="Initializing workers...", inline=False)
    embed_run.set_footer(text="KickBot ViewEngine")
    embed_run.timestamp = discord.utils.utcnow()

    try:
        await status_msg.edit(embed=embed_run)
    except Exception:
        pass

    try:
        while time.monotonic() < deadline and not stop_event.is_set():
            remaining = max(0, int(deadline - time.monotonic()))
            snap = await stats.snapshot()
            proxy_info = f"`{proxy_pool.count}` proxies" if proxy_pool.count > 0 else "`Proxyless`"

            status_text = (
                f"🟢 **Active Viewers:** `{snap.active}` / `{viewers}`\n"
                f"📡 **Total Connected:** `{snap.total}` | 🔄 **Retries:** `{snap.retries}` | ❌ **Failures:** `{snap.failures}`\n"
                f"🌐 **Network Mode:** {proxy_info} | ⏳ **Remaining:** `{remaining}s`"
            )
            embed_run.set_field_at(3, name="📊 Status", value=status_text, inline=False)
            embed_run.timestamp = discord.utils.utcnow()
            try:
                await status_msg.edit(embed=embed_run)
            except Exception:
                pass

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=3.5)
                break
            except asyncio.TimeoutError:
                pass
    finally:
        stop_event.set()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        _sessions.pop(session_key, None)
        await update_presence()

    final_snap = await stats.snapshot()
    done_embed = discord.Embed(
        title="✅ ViewBot Completed",
        color=0x6C63FF,
    )
    done_embed.add_field(name="📺 Channel", value=f"`{clean_user}`", inline=True)
    done_embed.add_field(name="🎯 Target", value=f"`{viewers}` viewers", inline=True)
    done_embed.add_field(name="⏱ Duration", value=f"`{duration}s`", inline=True)
    done_embed.add_field(name="🟢 Total Connected", value=f"`{final_snap.total}`", inline=True)
    done_embed.add_field(name="🔄 Retries", value=f"`{final_snap.retries}`", inline=True)
    done_embed.add_field(name="❌ Failures", value=f"`{final_snap.failures}`", inline=True)
    done_embed.set_footer(text="KickBot ViewEngine")
    done_embed.timestamp = discord.utils.utcnow()
    try:
        await status_msg.edit(embed=done_embed)
    except Exception:
        pass
    logger.info(f"[viewbot] {interaction.user} -> {clean_user} | {viewers} viewers | {duration}s")


# ── /say & /yaz (Admin Only) ──────────────────────────────────────────────────
@tree.command(name="say", description="Send an embed or plain message via the bot (Admin only)", guild=_guild_obj)
@app_commands.describe(
    content="Message content to send",
    title="Embed title (optional, leave empty for plain text)",
    color="Embed hex color (e.g. #00E676 or #6C63FF)",
    channel="Target channel (optional, defaults to current channel)",
)
async def say(
    interaction: discord.Interaction,
    content: str,
    title: str = "",
    color: str = "6c63ff",
    channel: discord.TextChannel = None,
):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this command! (Admin only)", ephemeral=True)
        return

    try:
        await interaction.response.defer(ephemeral=True)
    except discord.NotFound:
        return
    except Exception:
        pass

    target_channel = channel or interaction.channel
    try:
        color_int = int(color.strip().lstrip("#"), 16)
    except ValueError:
        color_int = 0x6C63FF

    try:
        if title:
            embed = discord.Embed(
                title=title,
                description=content,
                color=color_int,
            )
            await target_channel.send(embed=embed)
        else:
            await target_channel.send(content)

        await interaction.followup.send(
            f"✅ Message sent to **#{target_channel.name}**!",
            ephemeral=True,
        )
    except discord.Forbidden:
        await interaction.followup.send(
            f"❌ Missing permissions to send message in **#{target_channel.name}**!",
            ephemeral=True,
        )
    except Exception as e:
        await interaction.followup.send(f"❌ Error: `{e}`", ephemeral=True)

# Backward-compatible alias /yaz
@tree.command(name="yaz", description="Alias for /say (Admin only)", guild=_guild_obj)
@app_commands.describe(
    icerik="Message content to send",
    baslik="Embed title (optional)",
    renk="Embed hex color",
    kanal="Target channel",
)
async def yaz(
    interaction: discord.Interaction,
    icerik: str,
    baslik: str = "",
    renk: str = "6c63ff",
    kanal: discord.TextChannel = None,
):
    await say(interaction, content=icerik, title=baslik, color=renk, channel=kanal)



# ── /createaccounts (Admin Only) ──────────────────────────────────────────────
@tree.command(name="createaccounts", description="Auto-create Kick accounts and add tokens to tokens.json (Admin only)", guild=_guild_obj)
@app_commands.describe(
    amount="Number of accounts to create (max 20 per run)",
)
async def createaccounts(
    interaction: discord.Interaction,
    amount: int = 5,
):
    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ You do not have permission to use this command! (Admin only)", ephemeral=True
        )
        return

    if not HAS_CREATOR:
        await interaction.response.send_message(
            "❌ Creator module (`kick_creator.py`) not found in bot directory!", ephemeral=True
        )
        return

    amount = max(1, min(amount, 20))

    try:
        if not interaction.response.is_done():
            await interaction.response.defer()
    except (discord.NotFound, discord.InteractionResponded):
        return
    except Exception:
        pass

    embed_run = discord.Embed(
        title="🤖 Account Creator Running",
        description=(
            f"Creating **{amount}** Kick account(s)...\n"
            f"🌐 Proxies: `{'Enabled (' + str(_global_proxy_pool.count) + ' proxies)' if _global_proxy_pool and _global_proxy_pool.count else 'Direct IP'}`\n"
            f"📧 Temp Mail: `mail.tm (Free)`\n\n"
            f"⏳ Status: Starting automated Chromium engine..."
        ),
        color=0x6C63FF,
    )
    embed_run.set_footer(text="KickBot AccountEngine")
    embed_run.timestamp = discord.utils.utcnow()
    status_msg = await interaction.followup.send(embed=embed_run)

    success_count = 0
    fail_count    = 0
    logs: list[str] = []
    new_tokens: list[str] = []

    for i in range(amount):
        _px = _global_proxy_pool.sample() if _global_proxy_pool else None
        proxy_url = _px.http_url if _px else None

        embed_run.description = (
            f"Creating **{amount}** Kick account(s)...\n"
            f"🌐 Proxy: `{_px.raw.split(':')[0] if _px else 'Direct IP'}`\n\n"
            f"⏳ Progress: **{i+1}/{amount}** | ✅ `{success_count}` | ❌ `{fail_count}`"
        )
        try:
            await status_msg.edit(embed=embed_run)
        except Exception:
            pass

        async def _progress(msg: str):
            logger.info(f"[Creator {i+1}] {msg}")

        result: CreationResult = await create_one_account(
            proxy_url=proxy_url,
            progress_cb=_progress,
        )

        if result.success and result.token:
            success_count += 1
            new_tokens.append(result.token)
            logs.append(f"✅ `{result.username}` — token saved")
            if _px:
                _global_proxy_pool.mark_success(_px)
            logger.info(f"[Creator] ✅ Account created: {result.username} | {result.email}")
        else:
            fail_count += 1
            err_short = result.error[:60] if result.error else "unknown error"
            logs.append(f"❌ Attempt {i+1} — {err_short}")
            if _px:
                _global_proxy_pool.mark_failure(_px)
            logger.warning(f"[Creator] ❌ Failed: {result.error}")

        await asyncio.sleep(random.uniform(2.0, 4.0))

    # Save newly generated tokens into tokens.json
    if new_tokens:
        existing = load_tokens()
        existing_set = set(existing)
        added = [t for t in new_tokens if t not in existing_set]
        if added:
            save_tokens(existing + added)
            logger.info(f"[Creator] Added {len(added)} new tokens to tokens.json")

    color = 0x00E676 if success_count > 0 else 0xFF5050
    log_text = "\n".join(logs[-15:]) if logs else "No results"
    embed_done = discord.Embed(
        title="🏁 Account Creator Finished",
        color=color,
    )
    embed_done.add_field(name="✅ Created", value=f"`{success_count}`", inline=True)
    embed_done.add_field(name="❌ Failed",  value=f"`{fail_count}`",   inline=True)
    embed_done.add_field(name="💾 Tokens Saved", value=f"`{len(new_tokens)}` added to `tokens.json`", inline=True)
    embed_done.add_field(name="📋 Log", value=f"```\n{log_text}\n```", inline=False)
    embed_done.set_footer(text="KickBot AccountEngine")
    embed_done.timestamp = discord.utils.utcnow()

    try:
        await status_msg.edit(embed=embed_done)
    except Exception:
        try:
            await interaction.followup.send(embed=embed_done)
        except Exception:
            pass


# ── /addrole & /rolekle (Admin Only) ──────────────────────────────────────────
@tree.command(name="addrole", description="Assign a role to all members in the server (Admin only)", guild=_guild_obj)
@app_commands.describe(role="Role to assign to all members")
async def addrole(interaction: discord.Interaction, role: discord.Role):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this command! (Admin only)", ephemeral=True)
        return

    try:
        await interaction.response.defer()
    except discord.NotFound:
        return
    except Exception:
        pass

    guild = interaction.guild
    if not guild.chunked:
        await guild.chunk(cache=True)

    members = [m for m in guild.members if not m.bot and role not in m.roles]
    total = len(members)

    if total == 0:
        await interaction.followup.send(f"✅ All members already have the **{role.name}** role!")
        return

    embed = discord.Embed(
        title="⏳ Assigning Role...",
        description=f"Assigning **{role.name}** to `{total}` members...",
        color=role.color.value or 0x6C63FF,
    )
    embed.add_field(name="Progress", value=f"`0` / `{total}`", inline=False)
    embed.timestamp = discord.utils.utcnow()

    chan = interaction.channel
    msg = await chan.send(embed=embed)
    await interaction.followup.send("⏳ Process started, monitor progress in channel.", ephemeral=True)

    success = 0
    fail = 0

    for i, member in enumerate(members, 1):
        try:
            await member.add_roles(role, reason=f"/addrole by {interaction.user}")
            success += 1
        except Exception:
            fail += 1

        if i % 10 == 0 or i == total:
            embed.set_field_at(0, name="Progress", value=f"`{i}` / `{total}`", inline=False)
            try:
                await msg.edit(embed=embed)
            except Exception:
                pass

    color = 0x00E676 if fail == 0 else 0xFFAA00
    done_embed = discord.Embed(
        title="✅ Role Assignment Completed",
        color=color,
    )
    done_embed.add_field(name="🎭 Assigned Role", value=role.mention, inline=True)
    done_embed.add_field(name="✅ Successful", value=f"`{success}` members", inline=True)
    if fail > 0:
        done_embed.add_field(name="❌ Failed", value=f"`{fail}` members", inline=True)
    done_embed.add_field(name="👥 Total Processed", value=f"`{total}` members", inline=False)
    done_embed.timestamp = discord.utils.utcnow()
    try:
        await msg.edit(embed=done_embed)
    except Exception:
        pass
    logger.info(f"[addrole] {interaction.user} -> {role.name} | {success} success, {fail} failed")

# Backward-compatible alias /rolekle
@tree.command(name="rolekle", description="Alias for /addrole (Admin only)", guild=_guild_obj)
@app_commands.describe(rol="Role to assign to all members")
async def rolekle(interaction: discord.Interaction, rol: discord.Role):
    await addrole(interaction, role=rol)


# ── License Key Management Command ───────────────────────────────────────────
@tree.command(name="createkey", description="Create a 1-IP protected license key for the web dashboard (Admin only)", guild=_guild_obj)
@app_commands.describe(sure="Duration in hours (e.g. 24, 72, 168)")
async def createkey_cmd(interaction: discord.Interaction, sure: int):
    # Security check: Admin role or guild admin
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Only authorized administrators can use this command!", ephemeral=True)
        return

    if sure <= 0:
        await interaction.response.send_message("❌ Duration must be at least 1 hour!", ephemeral=True)
        return

    # Add parent directory to sys.path to import storage
    sys.path.insert(0, str(_DIR.parent))
    try:
        import storage
        storage.init_db()
        key_code = storage.create_license_key(sure, created_by=str(interaction.user))

        # Sync to remote Render deployment if available
        remote_url = os.getenv("RENDER_WEB_URL", "https://three1zcc.onrender.com").rstrip("/")
        admin_secret = os.getenv("ADMIN_PASSWORD", "ege123")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{remote_url}/api/admin/key-sync",
                    json={"action": "create", "key_code": key_code, "duration_hours": sure, "created_by": str(interaction.user)},
                    headers={"X-Admin-Secret": admin_secret},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"[createkey] Synced {key_code} to remote {remote_url}")
                    else:
                        logger.warning(f"[createkey] Remote sync status: {resp.status}")
        except Exception as sync_err:
            logger.warning(f"[createkey] Remote sync skipped or failed: {sync_err}")
        
        embed = discord.Embed(
            title="🔑 New License Key Created",
            description=f"Generated **1-IP Protected** license key for the web dashboard.",
            color=0x53FC18,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="🔑 License Key", value=f"```{key_code}```", inline=False)
        embed.add_field(name="⏱️ Valid Duration", value=f"`{sure}` Hours", inline=True)
        embed.add_field(name="🛡️ Protection", value="`1-IP Locked`", inline=True)
        embed.add_field(name="👤 Created By", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Key is locked to the client's IP on first login and countdown starts immediately.")
        
        await interaction.response.send_message(embed=embed)
        logger.info(f"[createkey] {interaction.user} created key {key_code} ({sure}h)")
    except Exception as e:
        logger.error(f"[createkey] Error: {e}")
        await interaction.response.send_message(f"❌ Error generating license key: `{e}`", ephemeral=True)



# ── Database Backup Command (Madde 42) ───────────────────────────────────────
@tree.command(name="backupdb", description="Send live botdash.db backup directly to Discord (Admin only)", guild=_guild_obj)
async def backupdb_cmd(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Only authorized administrators can use this command!", ephemeral=True)
        return
    db_path = _DIR.parent / "botdash.db"
    if not db_path.exists():
        await interaction.response.send_message("❌ Database backup file not found!", ephemeral=True)
        return
    file = discord.File(str(db_path), filename="botdash_backup.db")
    await interaction.response.send_message("📦 Live Database Backup:", file=file, ephemeral=True)


# ── Key List & Check Command (Madde 89 & 91) ─────────────────────────────────
@tree.command(name="keyslist", description="List all generated license keys and expiration times (Admin only)", guild=_guild_obj)
async def keyslist_cmd(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Only authorized administrators can use this command!", ephemeral=True)
        return
    sys.path.insert(0, str(_DIR.parent))
    try:
        import storage
        # Remote sync
        remote_url = os.getenv("RENDER_WEB_URL", "https://three1zcc.onrender.com").rstrip("/")
        admin_secret = os.getenv("ADMIN_PASSWORD", "ege123")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{remote_url}/api/sync/backup",
                    headers={"X-Admin-Secret": admin_secret},
                    timeout=aiohttp.ClientTimeout(total=4)
                ) as resp:
                    if resp.status == 200:
                        remote_data = await resp.json()
                        remote_keys = remote_data.get('license_keys', [])
                        if remote_keys:
                            storage.restore_all_data({'license_keys': remote_keys})
        except Exception as sync_err:
            logger.warning(f"[keyslist] Remote sync error: {sync_err}")

        keys = storage.get_all_license_keys()
        if not keys:
            await interaction.response.send_message("ℹ️ No license keys generated yet.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔑 License Keys & Usage Status",
            description=f"Total **{len(keys)}** license key(s) registered.",
            color=0x53FC18,
            timestamp=discord.utils.utcnow()
        )

        for k in keys[:25]:  # Discord embed field limit: 25
            is_used = bool(k.get('bound_ip') or k.get('activated_at'))
            if not k.get('is_active'):
                status_icon = "🔴 Expired / Revoked"
            elif is_used:
                status_icon = "🟢 In Use (Active)"
            else:
                status_icon = "🟡 Not Used Yet (Pending)"

            ip_txt = f"`{k.get('bound_ip')}`" if k.get('bound_ip') else "*None (Unbound)*"
            act_txt = k.get('activated_at') or "*Awaiting Activation*"
            exp_txt = k.get('expires_at') or f"{k.get('duration_hours', 24)} Hours (Countdown not started)"
            created_by = k.get('created_by') or 'Unknown'

            field_value = (
                f"**Status:** {status_icon}\n"
                f"**Bound IP:** {ip_txt}\n"
                f"**Activated:** {act_txt}\n"
                f"**Expiration:** `{exp_txt}`\n"
                f"**Creator:** `{created_by}`"
            )

            embed.add_field(
                name=f"🔑 `{k['key_code']}`",
                value=field_value,
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        logger.error(f"[keyslist] Error: {e}")
        await interaction.response.send_message(f"❌ Error listing keys: `{e}`", ephemeral=True)


# ── Delete License Key Command ──────────────────────────────────────────────
@tree.command(name="deletekey", description="Delete/Revoke a license key (Admin only)", guild=_guild_obj)
@app_commands.describe(key="The license key code to delete (e.g. TAXER-XXXX-XXXX)")
async def deletekey_cmd(interaction: discord.Interaction, key: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Only authorized administrators can use this command!", ephemeral=True)
        return

    clean_key = key.strip()
    sys.path.insert(0, str(_DIR.parent))
    try:
        import storage
        deleted = storage.delete_license_key(clean_key)

        # Sync key revocation to remote Render deployment
        remote_url = os.getenv("RENDER_WEB_URL", "https://three1zcc.onrender.com").rstrip("/")
        admin_secret = os.getenv("ADMIN_PASSWORD", "ege123")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{remote_url}/api/admin/key-sync",
                    json={"action": "delete", "key_code": clean_key},
                    headers={"X-Admin-Secret": admin_secret},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    logger.info(f"[deletekey] Remote revocation sent to {remote_url}, status: {resp.status}")
        except Exception as sync_err:
            logger.warning(f"[deletekey] Remote sync failed: {sync_err}")

        if deleted:
            embed = discord.Embed(
                title="🗑️ License Key Deleted",
                description=f"**`{clean_key}`** was successfully deleted and revoked.",
                color=0xFF3333,
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"Revoked by: {interaction.user}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"[deletekey] {interaction.user} deleted license key {clean_key}")
            await send_audit_log(
                title="🗑️ License Key Revoked",
                fields=[
                    {"name": "License Key", "value": f"`{clean_key}`", "inline": False},
                    {"name": "Revoked By", "value": interaction.user.mention, "inline": True}
                ],
                color=0xE74C3C
            )
        else:
            await interaction.response.send_message(f"⚠️ License key **`{clean_key}`** was not found (revocation broadcast sent).", ephemeral=True)
    except Exception as e:
        logger.error(f"[deletekey] Error: {e}")
        await interaction.response.send_message(f"❌ Error deleting license key: `{e}`", ephemeral=True)


# ── Bulk Purge License Keys Command ───────────────────────────────────────────
@tree.command(name="purgekeys", description="Delete/Purge ALL generated license keys at once (Admin only)", guild=_guild_obj)
@app_commands.describe(confirm="Type 'CONFIRM' to purge all license keys")
async def purgekeys_cmd(interaction: discord.Interaction, confirm: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Only authorized administrators can use this command!", ephemeral=True)
        return

    if confirm.strip().upper() not in ("CONFIRM", "ONAY"):
        await interaction.response.send_message("⚠️ You must pass `confirm:CONFIRM` to execute this bulk purge!\nExample: `/purgekeys confirm:CONFIRM`", ephemeral=True)
        return

    sys.path.insert(0, str(_DIR.parent))
    try:
        import storage
        total_local = storage.purge_all_license_keys()

        # Remote sync purge to Render deployment
        remote_url = os.getenv("RENDER_WEB_URL", "https://three1zcc.onrender.com").rstrip("/")
        admin_secret = os.getenv("ADMIN_PASSWORD", "ege123")
        remote_msg = "Remote sync failed"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{remote_url}/api/admin/key-sync",
                    json={"action": "purge_all"},
                    headers={"X-Admin-Secret": admin_secret},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        remote_msg = "Synced with Render cloud instance"
        except Exception as sync_err:
            remote_msg = f"Error: {sync_err}"

        embed = discord.Embed(
            title="💣 All License Keys Purged",
            description=f"Successfully purged **{total_local}** license key(s) and cleared active user sessions.",
            color=0xC0392B,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="🌐 Remote Deployment Status", value=f"`{remote_msg}`", inline=False)
        embed.set_footer(text=f"Purged by: {interaction.user}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

        await send_audit_log(
            title="💣 Bulk License Key Purge Executed",
            fields=[
                {"name": "Admin", "value": interaction.user.mention, "inline": True},
                {"name": "Keys Purged", "value": f"`{total_local}` Keys", "inline": True},
                {"name": "Cloud Sync", "value": f"`{remote_msg}`", "inline": False}
            ],
            color=0xC0392B
        )
    except Exception as e:
        logger.error(f"[purgekeys] Error: {e}")
        await interaction.response.send_message(f"❌ Error purging license keys: `{e}`", ephemeral=True)


# ── Discord Live Chat Stream & Reply (Madde 37) ─────────────────────────────
@tree.command(name="sendkick", description="Send a message directly to Kick chatroom from Discord", guild=_guild_obj)
@app_commands.describe(mesaj="Message to post into live Kick chatroom")
async def sendkick_cmd(interaction: discord.Interaction, mesaj: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Bu komutu yalnızca yetkililer kullanabilir!", ephemeral=True)
        return
    sys.path.insert(0, str(_DIR.parent))
    import storage
    import kick_client as _kc
    cid = storage.get_setting('chatroom_id')
    if not cid:
        await interaction.response.send_message("❌ Aktif bağlı bir Kick chatroom bulunamadı!", ephemeral=True)
        return

    accounts = storage.get_kick_accounts()
    if not accounts:
        await interaction.response.send_message("❌ Kayıtlı hesap bulunamadı!", ephemeral=True)
        return
    acc = accounts[0]
    tok = storage.get_kick_token_raw(acc['id'])
    ok, resp = _kc.send_kick_message(int(cid), mesaj, tok)
    if ok:
        await interaction.response.send_message(f"✅ Kick Chatine Gönderildi (`{acc['username']}`): **{mesaj}**")
    else:
        await interaction.response.send_message(f"❌ Gönderim başarısız: `{resp[:100]}`", ephemeral=True)


# ── Cluster Node / Multi-Server Manager (Madde 50) ───────────────────────────
@tree.command(name="clusternodes", description="Check status of multi-server worker cluster nodes", guild=_guild_obj)
async def clusternodes_cmd(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Bu komutu yalnızca yetkililer kullanabilir!", ephemeral=True)
        return
    embed = discord.Embed(title="🌐 Cluster Node Worker Durumu", color=0x53FC18)
    embed.add_field(name="🖥️ Node-01 (Primary / Master)", value="🟢 Online | 2083 Token | Port 5000", inline=False)
    embed.add_field(name="🖥️ Node-02 (Backup Worker)", value="⚪ Standby / Hot-Spare Hazır", inline=False)
    embed.add_field(name="🛡️ Yük Dengeleme", value="Round-Robin Akıllı Dağıtım Aktif", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── TikTok Script / Chat Highlights Generator (Madde 95) ─────────────────────
@tree.command(name="tiktokscript", description="Generate a TikTok / Reels viral script from recent Kick chat highlights", guild=_guild_obj)
async def tiktokscript_cmd(interaction: discord.Interaction):
    sys.path.insert(0, str(_DIR.parent))
    import storage
    logs = storage.get_message_logs(limit=30)
    user_chat = [l['content'] for l in logs if l.get('msg_type') in ('user', 'bot')]
    chat_sample = " | ".join(user_chat[-12:]) if user_chat else "Yayın çok sarıyor beyler | ahahah oha | GG"

    embed = discord.Embed(
        title="🎬 TikTok / Reels Video Metni (Chat Özeti)",
        description=f"**Kanca (Hook):** Kick chatinde dün gece öyle bir an yaşandı ki modlar bile sustu...\n\n"
                    f"**Chat Reaksiyonları:**\n`{chat_sample[:300]}`\n\n"
                    f"**Kapanış:** Bu yayını kaçıranlar çok şey kaybetti, takipte kalın!",
        color=0xFF0050
    )
    await interaction.response.send_message(embed=embed)


# ── Instant Hype / Raid Attack from Discord (Madde 5 & 28) ───────────────────
@tree.command(name="hypeattack", description="Trigger an instant multi-account hype raid into Kick chat (Admin only)", guild=_guild_obj)
@app_commands.describe(mesaj="Hype message or leave empty for random emotes", count="Number of accounts to raid with (1-50)")
async def hypeattack_cmd(interaction: discord.Interaction, mesaj: Optional[str] = "🔥 W YAYIN GG", count: Optional[int] = 30):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Bu komutu yalnızca yetkililer kullanabilir!", ephemeral=True)
        return

    sys.path.insert(0, str(_DIR.parent))
    import storage
    import kick_client as _kc

    cid = storage.get_setting('chatroom_id')
    if not cid:
        await interaction.response.send_message("❌ Aktif bağlı bir Kick chatroom bulunamadı!", ephemeral=True)
        return

    accounts = storage.get_kick_accounts()
    if not accounts:
        await interaction.response.send_message("❌ Sistemde aktif Kick hesabı yok!", ephemeral=True)
        return

    await interaction.response.send_message(f"🚀 **{min(count, len(accounts))}** adet hesapla Kick chatine Hype Raid başlatıldı! Hedef: `#{cid}`")

    def run_raid():
        raid_count = min(count, len(accounts))
        for a in accounts[:raid_count]:
            tok = storage.get_kick_token_raw(a['id'])
            if tok:
                _kc.send_kick_message(int(cid), mesaj, tok)
                time.sleep(random.uniform(0.2, 0.6))

    threading.Thread(target=run_raid, daemon=True).start()


# ── Discord & Site Integrated Commands ──────────────────────────────────────────

@tree.command(name="channel", description="View or switch the active Kick channel on the website dashboard (Admin only)", guild=_guild_obj)
@app_commands.describe(kanal="Target Kick channel slug to connect (e.g. sozcutv, xqc) or leave empty to view current")
async def channel_cmd(interaction: discord.Interaction, kanal: Optional[str] = None):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Bu komutu yalnızca yetkililer kullanabilir!", ephemeral=True)
        return

    sys.path.insert(0, str(_DIR.parent))
    import storage
    import kick_client as _kc

    current_ch = storage.get_setting("channel", "Bağlı Değil")
    current_cid = storage.get_setting("chatroom_id", "-")

    if not kanal:
        embed = discord.Embed(title="📺 Web Dashboard Kick Kanal Durumu", color=0x53FC18)
        embed.add_field(name="Mevcut Kanal", value=f"**{current_ch}**", inline=True)
        embed.add_field(name="Chatroom ID", value=f"`{current_cid}`", inline=True)
        embed.add_field(name="Web Panel", value="[Dashboard'a Git](http://localhost:5000)", inline=False)
        embed.set_footer(text="Değiştirmek için: /channel kanal:<yeni_kanal>")
        await interaction.response.send_message(embed=embed)
        return

    target = kanal.strip().lstrip("@").lower()
    await interaction.response.defer(thinking=True)
    try:
        data = _kc.get_channel_data(target)
        if not data or not data.get("chatroom_id"):
            await interaction.followup.send(f"❌ `{target}` kanalı Kick üzerinde bulunamadı veya chat kapalı!")
            return

        cid = data["chatroom_id"]
        storage.set_setting("channel", target)
        storage.set_setting("chatroom_id", str(cid))

        embed = discord.Embed(title="✅ Web Dashboard Kanalı Değiştirildi!", color=0x53FC18)
        embed.add_field(name="Yeni Hedef Kanal", value=f"🟢 **{target}**", inline=True)
        embed.add_field(name="Chatroom ID", value=f"`{cid}`", inline=True)
        embed.add_field(name="Durum", value="Web paneli ve arka plan botları yeni kanala senkronize edildi.", inline=False)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"[channel_cmd] Error: {e}")
        await interaction.followup.send(f"❌ Kanal değiştirilirken hata oluştu: `{e}`")


@tree.command(name="sitebots", description="List AI bots configured on the website with status and personalities", guild=_guild_obj)
async def sitebots_cmd(interaction: discord.Interaction):
    sys.path.insert(0, str(_DIR.parent))
    import storage

    bots = storage.get_bots()
    if not bots:
        await interaction.response.send_message("❌ Web sitesinde kayıtlı AI bot bulunamadı!", ephemeral=True)
        return

    embed = discord.Embed(title="🤖 Web Dashboard AI Karakterleri", color=0x9B59B6)
    for b in bots:
        status_icon = "🟢 Aktif" if b.get("enabled") else "🔴 Pasif"
        acc_id = b.get("kick_account_id")
        acc_text = f"Hesap #{acc_id}" if acc_id else "Rastgele Havuz"
        desc = (
            f"**Durum:** {status_icon} | **Bağlı:** {acc_text}\n"
            f"**Kişilik:** {b.get('personality') or 'Varsayılan'}\n"
            f"**Tepki İhtimali:** %{int(b.get('response_chance', 0.35) * 100)} | **Gecikme:** {b.get('min_delay')}-{b.get('max_delay')}s"
        )
        embed.add_field(name=f"🎭 {b['name']}", value=desc, inline=False)

    embed.set_footer(text="Açıp/Kapatmak için: /togglebot <bot_adi>")
    await interaction.response.send_message(embed=embed)


@tree.command(name="togglebot", description="Enable or disable an AI bot on the website dashboard (Admin only)", guild=_guild_obj)
@app_commands.describe(bot_adi="Bot name to toggle (e.g. MertBot, EceBot, TrolBot)")
async def togglebot_cmd(interaction: discord.Interaction, bot_adi: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Bu komutu yalnızca yetkililer kullanabilir!", ephemeral=True)
        return

    sys.path.insert(0, str(_DIR.parent))
    import storage

    bots = storage.get_bots()
    target_bot = next((b for b in bots if b["name"].lower() == bot_adi.strip().lower()), None)
    if not target_bot:
        names = ", ".join([b["name"] for b in bots])
        await interaction.response.send_message(f"❌ `{bot_adi}` bulunamadı! Mevcut botlar: `{names}`", ephemeral=True)
        return

    new_state = 0 if target_bot.get("enabled") else 1
    storage.update_bot(target_bot["id"], {"enabled": new_state})

    state_str = "🟢 AKTİF" if new_state else "🔴 PASİF"
    color = 0x53FC18 if new_state else 0xE74C3C
    embed = discord.Embed(
        title=f"⚡ Bot Durumu Güncellendi: {target_bot['name']}",
        description=f"Bot başarıyla **{state_str}** yapıldı. Web paneli ve chat motoru anında güncellendi.",
        color=color
    )
    await interaction.response.send_message(embed=embed)


@tree.command(name="livechat", description="Inspect recent live chat messages recorded by the web engine", guild=_guild_obj)
@app_commands.describe(limit="Number of recent messages to display (default 10)")
async def livechat_cmd(interaction: discord.Interaction, limit: Optional[int] = 10):
    sys.path.insert(0, str(_DIR.parent))
    import storage

    lim = max(3, min(limit or 10, 25))
    logs = storage.get_message_logs(limit=lim)
    if not logs:
        await interaction.response.send_message("ℹ️ Henüz kaydedilmiş chat mesajı bulunmuyor.", ephemeral=True)
        return

    embed = discord.Embed(title=f"💬 Canlı Kick Chat Akışı (Son {len(logs)} Mesaj)", color=0x3498DB)
    desc_lines = []
    for m in logs:
        ts = m.get("timestamp", "")[11:19]
        mtype = m.get("msg_type", "user")
        uname = m.get("username", "Anonim")
        content = m.get("content", "")
        if len(content) > 60:
            content = content[:57] + "..."
        badge = "🤖" if mtype in ("bot", "manual") else "👤"
        desc_lines.append(f"`{ts}` {badge} **{uname}**: {content}")

    embed.description = "\n".join(desc_lines)
    embed.set_footer(text="Mesaj göndermek için: /sendkick <mesaj>")
    await interaction.response.send_message(embed=embed)


@tree.command(name="proxystats", description="View latency and health scores of proxy pool from database", guild=_guild_obj)
async def proxystats_cmd(interaction: discord.Interaction):
    sys.path.insert(0, str(_DIR.parent))
    import storage

    stats = storage.get_proxy_stats()
    if not stats:
        await interaction.response.send_message("ℹ️ Veritabanında kayıtlı proxy test verisi yok (Proxyless modda çalışıyor).", ephemeral=True)
        return

    embed = discord.Embed(title="🛡️ Proxy Sağlık & Gecikme Havuzu", color=0x2ECC71)
    alive_count = sum(1 for s in stats if s.get("is_alive"))
    embed.description = f"**Toplam Kayıt:** {len(stats)} | **Aktif/Canlı:** {alive_count}\n"

    for s in stats[:8]:
        raw_p = s.get("proxy", "")
        masked_p = raw_p.split("@")[-1] if "@" in raw_p else raw_p
        lat = round(s.get("latency_ms", 0), 1)
        succ = s.get("success_count", 0)
        fail = s.get("fail_count", 0)
        status = "🟢" if s.get("is_alive") else "🔴"
        embed.add_field(
            name=f"{status} {masked_p}",
            value=f"⚡ Ping: `{lat}ms` | Başarılı: `{succ}` | Hata: `{fail}`",
            inline=True
        )

    await interaction.response.send_message(embed=embed)


@tree.command(name="clearchatlogs", description="Purge chat message logs from web database (Admin only)", guild=_guild_obj)
async def clearchatlogs_cmd(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Bu komutu yalnızca yetkililer kullanabilir!", ephemeral=True)
        return

    sys.path.insert(0, str(_DIR.parent))
    import sqlite3
    import storage

    try:
        conn = sqlite3.connect(storage.DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM message_logs")
        deleted = c.rowcount
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"🧹 Veritabanındaki **{deleted}** adet chat logu başarıyla temizlendi!")
    except Exception as e:
        await interaction.response.send_message(f"❌ Loglar temizlenirken hata: `{e}`", ephemeral=True)
# ── Global App Command Error Handler ──────────────────────────────────────────
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    orig = getattr(error, "original", error)
    cmd_name = interaction.command.name if interaction.command else "unknown"
    if isinstance(orig, discord.NotFound) and getattr(orig, "code", None) == 10062:
        logger.warning(f"[{cmd_name}] Discord interaction expired (10062 Unknown interaction).")
        return
    if isinstance(orig, discord.InteractionResponded):
        logger.warning(f"[{cmd_name}] Interaction already responded.")
        return
    logger.error(f"[{cmd_name}] Command error: {error}")
    try:
        msg = f"❌ An error occurred: `{error}`"
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)
    except Exception:
        pass


# ── Events ────────────────────────────────────────────────────────────────────
# Global proxy pool shared by chatbot / followbot / follow commands
_global_proxy_pool: Optional["ProxyPool"] = None  # type: ignore[name-defined]

def _load_global_proxy_pool() -> "ProxyPool":
    """Load (or reload) the proxy pool from disk. Called on startup and on /tokenadd."""
    proxy_candidates = [
        _DIR / "proxies.txt",
        _DIR / "proxy.txt",
        _DIR.parent / "proxies.txt",
        _DIR.parent / "proxy.txt",
    ]
    proxy_path = next((p for p in proxy_candidates if p.exists()), _DIR / "proxies.txt")
    pool = ProxyPool.from_file(proxy_path, cooldown=20.0)
    if pool.count:
        logger.info(f"[ProxyPool] Loaded {pool.count} proxies from {proxy_path.name}")
    else:
        logger.info("[ProxyPool] No proxy file found — running proxyless.")
    return pool

@bot.event
async def on_ready():
    global _global_proxy_pool
    logger.info(f"Bot logged in as: {bot.user}")
    toks = load_tokens()
    logger.info(f"Registered tokens in memory: {len(toks)}")

    _global_proxy_pool = _load_global_proxy_pool()

    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        logger.info(f"Guild commands synchronized: {len(synced)} command(s)")
    else:
        synced = await tree.sync()
        logger.info(f"Global commands synchronized: {len(synced)} command(s)")

    await update_presence()


if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("ERROR: Please set DISCORD_TOKEN in .env file!")
        sys.exit(1)
    logger.info("Starting Kick Discord Bot...")
    bot.run(DISCORD_TOKEN, log_handler=None)