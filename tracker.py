import os, json, time, asyncio, html, urllib.request, urllib.parse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.payments import GetStarGiftsRequest, GetResaleStarGiftsRequest, GetUniqueStarGiftRequest

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.environ["SESSION"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
STATE = "seen.json"
PER_GIFT = 20
RUN_SECONDS = 270
MAX_SEND = 40

def send(text, slug):
    kb = {"inline_keyboard": [[
        {"text": "🎁 Лот", "url": "https://t.me/nft/" + slug},
        {"text": "🔎 Get Gifts", "url": "https://t.me/share/url?url=https://t.me/nft/" + slug},
    ]]}
    p = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": "true", "reply_markup": json.dumps(kb)}
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                               urllib.parse.urlencode(p).encode(), timeout=20)
    except Exception as e:
        print("send error", e)

def price_of(g):
    ra = getattr(g, "resell_amount", None)
    if ra:
        return getattr(ra[0], "amount", ra[0])
    return getattr(g, "resell_stars", "?")

async def owner_of(client, u):
    uu, users = u, {}
    try:
        full = await client(GetUniqueStarGiftRequest(slug=u.slug))
        uu = getattr(full, "gift", u)
        users = {x.id: x for x in getattr(full, "users", [])}
    except Exception as e:
        print("unique error", e)
    oid = getattr(uu, "owner_id", None) or getattr(u, "owner_id", None)
    name = getattr(uu, "owner_name", None) or getattr(u, "owner_name", None)
    uid = getattr(oid, "user_id", None)
    if uid:
        us = users.get(uid)
        if not us:
            try:
                us = await client.get_entity(uid)
            except Exception:
                us = None
        un = getattr(us, "username", None) if us else None
        nm = html.escape(name or (getattr(us, "first_name", "") if us else "") or "профиль")
        s = f'<a href="tg://user?id={uid}">{nm}</a>'
        if un:
            s += f" @{html.escape(un)}"
        return s + f"\nID: <code>{uid}</code>", bool(un)
    if name and str(name).startswith("@"):
        return html.escape(str(name)), True
    if name:
        return html.escape(str(name)) + " (ID скрыт)", False
    return "скрыт", False

async def main():
    first = not os.path.exists(STATE)
    seen = {k.split(":")[0] for k in json.load(open(STATE))} if not first else set()
    end = time.time() + RUN_SECONDS
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        res = await client(GetStarGiftsRequest(hash=0))
        gifts = [g for g in getattr(res, "gifts", []) if getattr(g, "availability_resale", 0)]
        sent = 0
        while True:
            for gift in gifts:
                if time.time() > end:
                    break
                try:
                    r = await client(GetResaleStarGiftsRequest(gift_id=gift.id, offset="", limit=PER_GIFT))
                except Exception as e:
                    print("skip", gift.id, e)
                    await asyncio.sleep(2)
                    continue
                for u in r.gifts:
                    try:
                        if u.slug in seen:
                            continue
                        seen.add(u.slug)
                        if first or sent >= MAX_SEND:
                            continue
                        owner, has_user = await owner_of(client, u)
                        mark = "✅ " if has_user else ""
                        send(f"{mark}🎁 {html.escape(str(u.title))} #{u.num}\n💰 {price_of(u)} ⭐\n👤 {owner}", u.slug)
                        sent += 1
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        print("item error", e)
                await asyncio.sleep(0.5)
            json.dump(sorted(seen), open(STATE, "w"))
            first = False
            if time.time() > end:
                break

asyncio.run(main())
