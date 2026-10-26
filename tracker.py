import os, json, time, asyncio, html, urllib.request, urllib.parse, urllib.error
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.payments import GetStarGiftsRequest, GetResaleStarGiftsRequest
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.environ["SESSION"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
STATE = "seen.json"
PER_GIFT = 20
RUN_SECONDS = int(os.environ.get("RUN_SECONDS", 280))
MAX_SEND = 40
MAX_LOOKUPS = 8
TOPIC_GIRLS = 2
TOPIC_CHEAP = 3
TOPIC_MID = 4
TOPIC_RICH = 5
TOPIC_BLACK = 6
STARS_PER_TON = 150
MALE_EXCEPTIONS = {
    "никита", "илья", "саша", "женя", "миша", "паша", "гоша", "ваня", "коля",
    "петя", "вася", "лёша", "леша", "дима", "даня", "жора", "костя", "толя",
    "витя", "слава", "серёжа", "сережа", "андрюша", "юра", "федя", "сеня",
    "лёва", "лева", "тима", "стёпа", "степа", "гриша", "боря", "рома", "стас",
}
def send(text, slug, topic=None):
    text += f"\n🔗 <code>https://t.me/nft/{slug}</code>"
    kb = {"inline_keyboard": [
        [{"text": "🎁 Лот", "url": f"https://t.me/nft/{slug}"}],
        [{"text": "📤 Отправить ссылку в чат", "switch_inline_query": f"https://t.me/nft/{slug}"}],
    ]}
    p = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
        "reply_markup": json.dumps(kb),
    }
    if topic:
        p["message_thread_id"] = str(topic)
    try:
        data = urllib.parse.urlencode(p).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=data, timeout=20
        )
    except urllib.error.HTTPError as e:
        print("send error", e.code, e.read()[:300])
    except Exception as e:
        print("send error", e)
def price_of(g):
    ra = getattr(g, "resell_amount", None)
    if ra:
        return getattr(ra[0], "amount", ra[0])
    return getattr(g, "resell_stars", "?")
def ton_of(g):
    for x in (getattr(g, "resell_amount", None) or []):
        if "Ton" in type(x).__name__:
            return float(getattr(x, "amount", 0)) / 1e9
    try:
        return float(price_of(g)) / STARS_PER_TON
    except Exception:
        return 0.0
def price_text(g):
    for x in (getattr(g, "resell_amount", None) or []):
        if "Ton" in type(x).__name__:
            return f"{float(getattr(x, 'amount', 0)) / 1e9:g} TON"
    return f"{price_of(g)} ⭐"
def okey(u):
    oid = getattr(u, "owner_id", None)
    uid = getattr(oid, "user_id", None)
    if uid:
        return f"u{uid}"
    return "a" + str(getattr(u, "owner_address", "") or getattr(u, "owner_name", "") or u.slug)
def attrs(u):
    out = {}
    for a in getattr(u, "attributes", []) or []:
        n = type(a).__name__
        name = getattr(a, "name", None)
        if not name:
            continue
        if "Model" in n:
            out["model"] = name
        elif "Backdrop" in n:
            out["back"] = name
        elif "Pattern" in n:
            out["pat"] = name
    return out
def is_girl(name):
    parts = "".join(c for c in (name or "") if c.isalpha() or c == " ").split()
    if not parts:
        return False
    first = parts[0].lower()
    if first in MALE_EXCEPTIONS:
        return False
    return first.endswith(("а", "я", "a"))
def topic_of(lot, back="", name=""):
    if back and ("black" in back.lower() or "черн" in back.lower() or "чёрн" in back.lower()):
        return TOPIC_BLACK
    if is_girl(name):
        return TOPIC_GIRLS
    ton = ton_of(lot)
    if ton < 8:
        return TOPIC_CHEAP
    if ton <= 15:
        return TOPIC_MID
    return TOPIC_RICH
async def owner_of(client, u):
    oid = getattr(u, "owner_id", None)
    uid = getattr(oid, "user_id", None)
    plain = str(getattr(u, "owner_name", "") or "")
    if uid:
        try:
            ent = await client.get_entity(uid)
            plain = " ".join(x for x in (ent.first_name, ent.last_name) if x) or ent.username or str(uid)
        except Exception:
            pass
            return f'<a href="tg://user?id={uid}">{html.escape(plain or str(uid))}</a>', True, plain
    addr = str(getattr(u, "owner_address", "") or "")
    text = html.escape(plain or addr or "скрыт")
    return text, False, plain
async def bot_owner(client, bot, slug, label):
    try:
        texts, links = [], []
        async with client.conversation(bot, timeout=20) as conv:
            await conv.send_message(f"https://t.me/nft/{slug}")
            for _ in range(2):
                try:
                    r = await conv.get_response()
                except Exception:
                    break
                print("BOT", bot, repr(r.raw_text[:300]))
                texts.append(r.raw_text)
                for ent, txt in (r.get_entities_text() or []):
                    url = getattr(ent, "url", None)
                    uid = getattr(ent, "user_id", None)
                    if uid:
                        links.append(f"tg://user?id={uid}")
                    elif url and "t.me/" in url and "/nft/" not in url:
                        links.append(url)
                if "ладел" in r.raw_text:
                    break
        line = ""
        for t in texts:
            line = next((l for l in t.splitlines() if "ладел" in l), "")
            if line:
                break
        out = html.escape(line.strip())
        if links:
            out += "\n" + links[0].replace("http://", "https://")
        return f"🔎 {label}: {out}" if (line or links) else ""
    except Exception as e:
        print("bot error", bot, e)
        return ""
async def main():
    first = not os.path.exists(STATE)
    seen = {k.split(":")[0] for k in json.load(open(STATE))} if not first else set()
    end = time.time() + RUN_SECONDS
    sent = 0
    lookups = 0
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        res = await client(GetStarGiftsRequest(hash=0))
        gifts = [g for g in getattr(res, "gifts", []) if getattr(g, "availability_resale", 0)]
        while True:
            pending = {}
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
                    if u.slug in seen:
                        continue
                    seen.add(u.slug)
                    if first:
                        continue
                    pending.setdefault(okey(u), []).append(u)
                await asyncio.sleep(0.5)
            for lots in pending.values():
                if sent >= MAX_SEND:
                    break
                try:
                    lots.sort(key=ton_of)
                    main_lot = lots[0]
                    owner, has_user, plain_name = await owner_of(client, main_lot)
                    if not has_user and lookups < MAX_LOOKUPS:
                        lookups += 1
                        for bot, label in (("getSendGiftsProBot", "Get Gifts"), ("seetgbot", "see.tg")):
                            so = await bot_owner(client, bot, main_lot.slug, label)
                            await asyncio.sleep(3)
                            if so:
                                owner += "\n" + so
                    a = attrs(main_lot)
                    mark = "✅ " if has_user else ""
                    text = f"{mark}🎁 {html.escape(str(main_lot.title))} #{main_lot.num}\n💰 {price_text(main_lot)}"
                    if a:
                        text += "\n🎨 " + html.escape(" · ".join(x for x in (a.get("model"), a.get("back"), a.get("pat")) if x))
                    text += f"\n👤 {owner}"
                    if len(lots) > 1:
                        extra = [
                            f"{html.escape(str(x.title))} #{x.num} ({price_text(x)}) t.me/nft/{x.slug}"
                            for x in lots[1:6]
                        ]
                        text += f"\n\n➕ Ещё лотов этого продавца: {len(lots) - 1}\n" + "\n".join(extra)
                    send(text, main_lot.slug, topic_of(main_lot, a.get("back", ""), plain_name))
                    sent += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print("item error", e)
            json.dump(sorted(seen), open(STATE, "w"))
            first = False
            if time.time() > end:
                break
            await asyncio.sleep(5)
asyncio.run(main())
