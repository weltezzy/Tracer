
import os
import json
import time
import asyncio
import html
import urllib.request
import urllib.parse

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.payments import (
    GetStarGiftsRequest,
    GetResaleStarGiftsRequest,
    GetUniqueStarGiftRequest,
)

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.environ["SESSION"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

STATE_FILE = "seen.json"
OWNERS_FILE = "owners.json"
PER_GIFT = 50
RUN_SECONDS = 270
MAX_SEND = 100
POLL_DELAY = 1


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp, path)


def send_message(text, slug):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    gift_url = "https://t.me/nft/" + slug

    keyboard = {
        "inline_keyboard": [
            [{"text": "🎁 Открыть NFT", "url": gift_url}],
            [
                {"text": "🔎 Get Gifts",
                 "url": "https://t.me/getSendGiftsProBot?start=" + slug},
                {"text": "📊 see.tg",
                 "url": "https://t.me/seetgbot?start=" + slug},
            ],
        ]
    }

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": json.dumps(keyboard),
    }

    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode(),
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode())
        if not result.get("ok"):
            print("Send error:", result)
            return False
        return True
    except Exception as e:
        print("Send error:", repr(e))
        return False


def get_price(gift):
    amounts = getattr(gift, "resell_amount", None)
    if amounts:
        return getattr(amounts[0], "amount", amounts[0])
    return getattr(gift, "resell_stars", "?")


def price_number(gift):
    try:
        return int(get_price(gift))
    except (ValueError, TypeError):
        return 10**12


async def get_owner(client, gift, owners):
    unique = gift
    users = {}

    try:
        result = await client(
            GetUniqueStarGiftRequest(slug=gift.slug)
        )
        unique = getattr(result, "gift", gift)
        users = {
            user.id: user
            for user in getattr(result, "users", [])
        }
    except Exception as e:
        print("Owner lookup error:", gift.slug, repr(e))

    owner = getattr(unique, "owner_id", None)
    uid = getattr(owner, "user_id", None)
    name = getattr(unique, "owner_name", None)
    address = getattr(unique, "owner_address", None)

    if uid:
        user = users.get(uid)

        if user is None:
            try:
                user = await client.get_entity(uid)
            except Exception as e:
                print("User lookup error:", repr(e))

        if user is not None:
            username = getattr(user, "username", None)
            display = (
                getattr(user, "first_name", None)
                or name
                or "Владелец"
            )

            if username:
                owners[str(uid)] = {
                    "username": username,
                    "name": display,
                    "updated": int(time.time()),
                }

            text = (
                f'<a href="tg://user?id={uid}">'
                f'{html.escape(str(display))}</a>'
            )

            if username:
                text += f" (@{html.escape(username)})"
                return text, True

            return text + f"\nID: <code>{uid}</code>", False

        return (
            html.escape(str(name or "Владелец"))
            + f"\nID: <code>{uid}</code>",
            False,
        )

    if name:
        if str(name).startswith("@"):
            return html.escape(str(name)), True
        return html.escape(str(name)) + "\n🔒 ID скрыт", False

    if address:
        return (
            "🔒 Username не предоставлен\n"
            "Адрес: <code>" + html.escape(str(address)) + "</code>",
            False,
        )

    return "🔒 Владелец не предоставлен Telegram", False


async def main():
    seen = set(load_json(STATE_FILE, []))
    owners = load_json(OWNERS_FILE, {})

    async with TelegramClient(
        StringSession(SESSION), API_ID, API_HASH
    ) as client:
        response = await client(GetStarGiftsRequest(hash=0))
        gift_types = [
            g for g in getattr(response, "gifts", [])
            if getattr(g, "availability_resale", 0)
        ]

        print("Gift types:", len(gift_types))

        # Первый запуск: запоминаем существующие лоты.
        if not os.path.exists(STATE_FILE):
            for gift_type in gift_types:
                try:
                    result = await client(
                        GetResaleStarGiftsRequest(
                            gift_id=gift_type.id,
                            offset="",
                            limit=PER_GIFT,
                        )
                    )
                    for item in getattr(result, "gifts", []):
                        seen.add(item.slug)
                except Exception as e:
                    print("Initial scan error:", repr(e))

                await asyncio.sleep(POLL_DELAY)

            save_json(STATE_FILE, sorted(seen))
            save_json(OWNERS_FILE, owners)
            print("Initial scan complete. Restart to monitor new listings.")
            return

        deadline = time.time() + RUN_SECONDS
        sent = 0

        while time.time() < deadline and sent < MAX_SEND:
            new_items = []

            for gift_type in gift_types:
                if time.time() >= deadline:
                    break

                try:
                    result = await client(
                        GetResaleStarGiftsRequest(
                            gift_id=gift_type.id,
                            offset="",
                            limit=PER_GIFT,
                        )
                    )

                    for item in getattr(result, "gifts", []):
                        if item.slug not in seen:
                            seen.add(item.slug)
                            new_items.append(item)

                except Exception as e:
                    print("Market scan error:", repr(e))

                await asyncio.sleep(POLL_DELAY)

            new_items.sort(key=price_number)

            for gift in new_items:
                if sent >= MAX_SEND:
                    break

                try:
                    owner_text, has_username = await get_owner(
                        client, gift, owners
                    )

                    mark = "✅ " if has_username else ""
                    text = (
                        f"{mark}🎁 {html.escape(str(gift.title))} "
                        f"#{gift.num}\n"
                        f"💰 {get_price(gift)} ⭐\n"
                        f"👤 {owner_text}"
                    )

                    if send_message(text, gift.slug):
                        sent += 1

                except Exception as e:
                    print("Gift processing error:", repr(e))

                await asyncio.sleep(0.5)

            save_json(STATE_FILE, sorted(seen))
            save_json(OWNERS_FILE, owners)

        print("Finished. Notifications sent:", sent)


if __name__ == "__main__":
    asyncio.run(main())

