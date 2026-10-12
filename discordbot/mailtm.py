"""
mailtm.py — Async mail.tm API wrapper
Free temporary email service, no API key needed.
"""
import asyncio
import random
import string
import aiohttp
from typing import Optional

MAILTM_BASE = "https://api.mail.tm"

def _rand_str(n: int = 10) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

class MailTmAccount:
    def __init__(self, address: str, password: str, token: str):
        self.address = address
        self.password = password
        self.token = token

    async def wait_for_mail(
        self,
        subject_contains: str = "",
        timeout: int = 90,
        poll_interval: float = 3.0,
    ) -> Optional[dict]:
        """Poll inbox until a matching mail arrives or timeout."""
        headers = {"Authorization": f"Bearer {self.token}"}
        deadline = asyncio.get_event_loop().time() + timeout
        async with aiohttp.ClientSession() as s:
            while asyncio.get_event_loop().time() < deadline:
                try:
                    async with s.get(f"{MAILTM_BASE}/messages", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                        if r.status == 200:
                            data = await r.json()
                            msgs = data.get("hydra:member", [])
                            for m in msgs:
                                if not subject_contains or subject_contains.lower() in m.get("subject", "").lower():
                                    # Fetch full message
                                    msg_id = m["id"]
                                    async with s.get(f"{MAILTM_BASE}/messages/{msg_id}", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as mr:
                                        if mr.status == 200:
                                            return await mr.json()
                except Exception:
                    pass
                await asyncio.sleep(poll_interval)
        return None


async def create_mailTm_account(domain: str = "") -> Optional[MailTmAccount]:
    """Create a new mail.tm account and return credentials + token."""
    async with aiohttp.ClientSession() as s:
        # Get available domains
        if not domain:
            try:
                async with s.get(f"{MAILTM_BASE}/domains", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        domains = data.get("hydra:member", [])
                        if domains:
                            domain = domains[0]["domain"]
            except Exception:
                pass
        if not domain:
            domain = "mail.tm"

        address = f"{_rand_str(10)}@{domain}"
        password = _rand_str(14) + "A1!"

        # Create account
        try:
            async with s.post(
                f"{MAILTM_BASE}/accounts",
                json={"address": address, "password": password},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status not in (200, 201):
                    return None
        except Exception:
            return None

        # Get token
        try:
            async with s.post(
                f"{MAILTM_BASE}/token",
                json={"address": address, "password": password},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    token = data.get("token", "")
                    if token:
                        return MailTmAccount(address, password, token)
        except Exception:
            return None

    return None
