from __future__ import annotations

import asyncio
import random
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from aiohttp import web

from . import config, user_data

code_cache: dict[int, tuple[str, bool, str, datetime]] = {}


def cleanup_expired_codes():
    now = datetime.utcnow()
    for code in list(code_cache):
        if now > code_cache[code][3]:
            code_cache.pop(code, None)


def _send_email_sync(email: str, code: int):
    my_email = config.email_for_auth_messages
    password = config.app_password_for_auth_messages
    msg = MIMEText(
        f"Your account managment code is: {code}\n\n"
        "To continue this process, enter the code in the \"Confirm action\" "
        "menu in the game settings.\nThis code expires in 15 minutes.")
    msg["Subject"] = "Your account managment code"
    msg["From"] = my_email
    msg["To"] = email
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(my_email, password)
        server.send_message(msg)


async def send_code_email(email: str, code: int):
    await asyncio.get_running_loop().run_in_executor(None, _send_email_sync, email, code)


async def init_account_action(request: web.Request, is_link: bool) -> web.Response:
    userid = request.query.get("userId", "")
    email = request.query.get("email", "")
    if not userid or not email:
        return web.Response(status=400)
    gdkey = await user_data.get_gdkey_from_user_id(userid)
    if not gdkey:
        return web.Response(status=500)
    acc = await user_data.get_account_from_gdkey(gdkey)
    if acc is None:
        return web.Response(status=404)
    udkey = acc.udkey
    code = random.randint(100000, 999999)
    while code in code_cache:
        code = random.randint(100000, 999999)
    await send_code_email(email, code)
    code_cache[code] = (email, is_link, udkey,
                        datetime.utcnow() + timedelta(minutes=15))
    return web.Response(status=200, content_type="application/json")
