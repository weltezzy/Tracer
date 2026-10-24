
import os, json, asyncio, urllib.request, urllib.parse
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

def send(text):
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data, timeout=20)

def price_of(g):
    ra = getattr(g, "resell_amount", None)
    if ra:
        return getattr(ra[0], "amount", ra[0])
    return getattr(g, "resell_stars", "?")

async def main():
    first = not os.path.exists(STATE)
    seen = set(json.load(open(STATE))) if not first else set()
    new_seen = set(seen)
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
            for u in r.gifts:
                price = price_of(u)
                key = f"{u.slug}:{price}"
                new_seen.add(key)
                if key in seen or first:
                    continue 
owner = None
owner_id = getattr(u, "owner_id", None)

# Сначала пытаемся получить публичный username
if owner_id:
    try:
        entity = await client.get_entity(owner_id)
        username = getattr(entity, "username", None)

        if username:
            owner = f"@{username}"
    except Exception as exc:
        print("Username lookup failed:", repr(exc))

# Если username недоступен, показываем имя из данных подарка
if not owner:
    owner = getattr(u, "owner_name", None) or "не удалось определить"
                send(f"🎁 {u.title} #{u.num}\n💰 {price} ⭐\n👤 {owner or 'скрыт'}\n🔗 https://t.me/nft/{u.slug}")
                await asyncio.sleep(0.5)
            await asyncio.sleep(1)
    json.dump(sorted(new_seen), open(STATE, "w"))

asyncio.run(main())
