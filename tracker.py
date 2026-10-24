import os, json, asyncio, html, urllib.request, urllib.parse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.payments import GetStarGiftsRequest, GetResaleStarGiftsRequest

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.environ["SESSION"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
STATE = "seen.json"
PER_GIFT = 5
MAX_SEND = 4
dbg = 0

def send(text):
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data, timeout=20)
    except Exception as e:
        print("send error", e)

def price_of(g):
    ra = getattr(g, "resell_amount", None)
    if ra:
        return getattr(ra[0], "amount", ra[0])
    return getattr(g, "resell_stars", "?")

async def owner_of(client, u, users):
    global dbg
    oid = getattr(u, "owner_id", None)
    oname = getattr(u, "owner_name", None)
    oaddr = getattr(u, "owner_address", None)
    if dbg < 3:
        dbg += 1
        print("DEBUG owner_id=", oid, "owner_name=", oname, "owner_address=", oaddr)
    uid = getattr(oid, "user_id", None)
    if uid:
        user = users.get(uid)
        if not user:
            try:
                user = await client.get_entity(uid)
            except Exception:
                user = None
        name = ""
        uname = ""
        if user:
            name = " ".join(x for x in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if x)
            uname = getattr(user, "username", None) or ""
        name = html.escape(name or oname or "профиль")
        s = f'<a href="tg://user?id={uid}">{name}</a>'
        if uname:
            s += f" @{html.escape(uname)}"
        return s + f" (id {uid})"
    if oaddr:
        return f"кошелёк {html.escape(str(oaddr))}"
    if oname:
        return f"{html.escape(oname)} (ID скрыт)"
    return "скрыт"

async def main():
    first = not os.path.exists(STATE)
    seen = set(json.load(open(STATE))) if not first else set()
    new_seen = set(seen)
    sent = 0
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        res = await client(GetStarGiftsRequest(hash=0))
        gifts = [g for g in getattr(res, "gifts", []) if getattr(g, "availability_resale", 0)]
        for gift in gifts:
            try:
                r = await client(GetResaleStarGiftsRequest(gift_id=gift.id, offset="", limit=PER_GIFT))
            except Exception as e:
                print("skip", gift.id, e)
                await asyncio.sleep(2)
                continue
            users = {x.id: x for x in getattr(r, "users", [])}
            for u in r.gifts:
                try:
                    price = price_of(u)
                    key = f"{u.slug}:{price}"
                    new_seen.add(key)
                    if key in seen or first:
                        continue
                    if sent >= MAX_SEND:
                        continue
                    owner = await owner_of(client, u, users)
                    send(f"🎁 {html.escape(str(u.title))} #{u.num}\n💰 {price} ⭐\n👤 {owner}\n🔗 https://t.me/nft/{u.slug}")
                    sent += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    print("item error", e)
            await asyncio.sleep(1)
    json.dump(sorted(new_seen), open(STATE, "w"))

asyncio.run(main())
