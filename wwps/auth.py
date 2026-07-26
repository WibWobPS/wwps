from __future__ import annotations

import asyncio
import re
import secrets
import smtplib
import time
from datetime import UTC, datetime, timedelta
from email.mime.text import MIMEText

from aiohttp import web

from . import config, logging_setup, metrics, user_data, validate

log = logging_setup.get(__name__)

CODE_TTL_MINUTES = 15
MAX_PENDING_CODES = 1000
MAX_ATTEMPTS = 5
ATTEMPT_WINDOW_SECONDS = 900
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,}$")

code_cache: dict[int, tuple[str, bool, str, datetime]] = {}
_attempts: dict[str, tuple[int, float]] = {}


class AuthRateLimited(Exception):
    pass


def reset_state():
    code_cache.clear()
    _attempts.clear()


def _now() -> datetime:
    return datetime.now(UTC)


def cleanup_expired_codes():
    now = _now()
    for code in list(code_cache):
        if now > code_cache[code][3]:
            code_cache.pop(code, None)
    cutoff = time.monotonic() - ATTEMPT_WINDOW_SECONDS
    for key, (_, stamp) in list(_attempts.items()):
        if stamp < cutoff:
            _attempts.pop(key, None)


def is_valid_email(email: str) -> bool:
    if not email or len(email) > 254 or any(c in email for c in "\r\n\t"):
        return False
    return EMAIL_RE.match(email) is not None


def attempts_left(key: str) -> int:
    count, stamp = _attempts.get(key, (0, 0.0))
    if time.monotonic() - stamp > ATTEMPT_WINDOW_SECONDS:
        return MAX_ATTEMPTS
    return max(0, MAX_ATTEMPTS - count)


def record_attempt(key: str):
    count, stamp = _attempts.get(key, (0, 0.0))
    if time.monotonic() - stamp > ATTEMPT_WINDOW_SECONDS:
        count = 0
    _attempts[key] = (count + 1, time.monotonic())


def clear_attempts(key: str):
    _attempts.pop(key, None)


def _new_code() -> int:
    for _ in range(64):
        code = 100000 + secrets.randbelow(900000)
        if code not in code_cache:
            return code
    raise AuthRateLimited("no free code slot")


def _send_email_sync(email: str, code: int):
    my_email = config.email_for_auth_messages
    password = config.app_password_for_auth_messages
    msg = MIMEText(
        f"Your account management code is: {code}\n\n"
        "To continue this process, enter the code in the \"Confirm action\" "
        f"menu in the game settings.\nThis code expires in {CODE_TTL_MINUTES} "
        "minutes.")
    msg["Subject"] = "Your account management code"
    msg["From"] = my_email
    msg["To"] = email
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.starttls()
        server.login(my_email, password)
        server.send_message(msg)


async def send_code_email(email: str, code: int):
    await asyncio.get_running_loop().run_in_executor(None, _send_email_sync, email, code)


def redeem(code: int, udkey: str) -> tuple[str, bool] | None:
    """Consume a pending code. Returns (email, is_link) or None when invalid."""
    cleanup_expired_codes()
    entry = code_cache.get(code)
    if entry is None:
        return None
    email, is_link, owner_udkey, expires = entry
    if _now() > expires:
        code_cache.pop(code, None)
        return None
    if owner_udkey != udkey:
        return None
    code_cache.pop(code, None)
    return email, is_link


async def init_account_action(request: web.Request, is_link: bool) -> web.Response:
    cleanup_expired_codes()
    userid = request.query.get("userId", "")
    email = request.query.get("email", "")
    if not userid or not is_valid_email(email):
        return web.Response(status=400)
    if not validate.is_key_like(userid):
        return web.Response(status=400)
    if not config.email_for_auth_messages or not config.app_password_for_auth_messages:
        log.warning("account link requested but no mail account is configured")
        return web.Response(status=503)
    if len(code_cache) >= MAX_PENDING_CODES:
        metrics.incr("auth_code_cache_full")
        return web.Response(status=503)

    email_key = f"mail:{email.lower()}"
    if attempts_left(email_key) <= 0:
        metrics.incr("auth_code_throttled")
        log.warning("too many code requests for %s", logging_setup.mask(email))
        return web.Response(status=429)
    record_attempt(email_key)

    gdkey = await user_data.get_gdkey_from_user_id(userid)
    if not gdkey:
        return web.Response(status=404)
    acc = await user_data.get_account_from_gdkey(gdkey)
    if acc is None or not acc.udkey:
        return web.Response(status=404)

    code = _new_code()
    try:
        await send_code_email(email, code)
    except Exception:
        metrics.incr("auth_mail_failed")
        log.error("could not send the account code to %s",
                  logging_setup.mask(email), exc_info=True)
        return web.Response(status=502)
    code_cache[code] = (email, is_link, acc.udkey,
                        _now() + timedelta(minutes=CODE_TTL_MINUTES))
    metrics.incr("auth_codes_sent")
    log.info("sent an account %s code to %s", "link" if is_link else "restore",
             logging_setup.mask(email))
    return web.Response(status=200, content_type="application/json")
