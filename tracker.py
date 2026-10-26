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
CL = "claims.json"
PER_GIFT = 20
RUN_SECONDS = int(os.environ.get("RUN_SECONDS", 280))
MAX_SEND = 40
MAX_LOOKUPS = 16
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


def api_sync(method, **p):
    for _ in range(3):
        try:
            r = urllib.request.urlopen(
                f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
                urllib.parse.urlencode(p).encode(), timeout=40)
            return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read())
            except Exception:
                body = {}
            if e.code == 429:
                time.sleep(min(body.get("parameters", {}).get("retry_after", 5), 30))
                continue
            print("api error", method, e.code, body.get("description"))
            return body or {"ok": False}
        except Exception as e:
            print("api error", method, e)
            return {"ok": False}
    return {"ok": False}


async def api(method, **p):
    return await asyncio.to_thread(lambda: api_sync(method, **p))


def load_st():
    try:
        st = json.load(open(CL))
    except Exception:
        st = {}
    for k, v in (("offset", 0), ("claimed", {}), ("lots", {})):
        st.setdefault(k, v)
    return st


def save_st(st):
    if len(st["lots"]) > 500:
        for k in list(st["lots"])[:-500]:
            st["lots"].pop(k, None)
    json.dump(st, open(CL, "w"))


async def send(text, slug, topic=None):
    text += f"\n🔗 <code>https://t.me/nft/{slug}</code>"
    kb = {"inline_keyboard": [
        [{"text": "✅ Занять", "callback_data": f"c:{slug}"}],
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
    r = await api("sendMessage", **p)
    return bool(r.get("ok"))


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


def status_lines(ent):
    if not ent or not hasattr(ent, "first_name"):
        return ""
    s = getattr(ent, "status", None)
    n = type(s).__name__
    if n == "UserStatusOnline":
        on = "в сети сейчас"
    elif n == "UserStatusOffline":
        on = "был(а) " + s.was_online.strftime("%d.%m %H:%M")
    elif n == "UserStatusRecently":
        on = "недавно"
    else:
        on = "скрыто"
    prem = "С премиумом" if getattr(ent, "premium", False) else "Обычный"
    return f"\n📍 <b>Онлайн:</b> {on}\n💎 <b>Статус:</b> {prem}"


async def owner_of(client, u):
    oid = getattr(u, "owner_id", None)
    uid = getattr(oid, "user_id", None)
    plain = str(getattr(u, "owner_name", "") or "")
    if uid:
        ent = None
        try:
            ent = await client.get_entity(uid)
            plain = " ".join(x for x in (ent.first_name, ent.last_name) if x) or ent.username or str(uid)
        except Exception:
            pass
        link = f'<a href="tg://user?id={uid}">{html.escape(plain or str(uid))}</a>'
        un = getattr(ent, "username", None) if ent else None
        if un:
            link += f" @{html.escape(un)}"
        return link, True, plain, ent
    addr = str(getattr(u, "owner_address", "") or "")
    text = html.escape(plain or addr or "скрыт")
    return text, False, plain, None


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


async def handle_claim(client, cq, st):
    slug = cq["data"][2:]
    uid = cq["from"]["id"]
    name = cq["from"].get("first_name") or cq["from"].get("username") or "user"
    msg = cq["message"]
    if slug in st["claimed"]:
        await api("answerCallbackQuery", callback_query_id=cq["id"],
                  text="Уже занял: " + st["claimed"][slug], show_alert="true")
        return
    r = await api("sendMessage", chat_id=uid, text="⏳ Лот за тобой, собираю данные…")
    if not r.get("ok"):
        await api("answerCallbackQuery", callback_query_id=cq["id"],
                  text="Сначала открой бота, нажми Start и снова «Занять»", show_alert="true")
        return
    st["claimed"][slug] = name
    save_st(st)
    await api("answerCallbackQuery", callback_query_id=cq["id"], text="Лот твой, данные в личке")
    kb = [[{"text": ("🔒 Занял: " + name)[:60], "callback_data": "x"}],
          [{"text": "🎁 Лот", "url": f"https://t.me/nft/{slug}"}]]
    await api("editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
              reply_markup=json.dumps({"inline_keyboard": kb}))
    p = dict(chat_id=msg["chat"]["id"], parse_mode="HTML", reply_to_message_id=msg["message_id"],
             text=f'🔒 <a href="tg://user?id={uid}">{html.escape(name)}</a> занял лот {slug}')
    if msg.get("message_thread_id"):
        p["message_thread_id"] = msg["message_thread_id"]
    await api("sendMessage", **p)
    gg = await bot_owner(client, "getSendGiftsProBot", slug, "Get Gifts")
    text = (f"🔒 <b>Ты занял лот</b>\nhttps://t.me/nft/{slug}\n\n"
            f"👤 {st['lots'].get(slug, 'скрыт')}" + (f"\n{gg}" if gg else ""))
    await api("sendMessage", chat_id=uid, text=text[:4000], parse_mode="HTML",
              disable_web_page_preview="true")


async def poller(client, st, end, tasks):
    while time.time() < end:
        r = await api("getUpdates", offset=st["offset"], timeout=8,
                      allowed_updates=json.dumps(["callback_query"]))
        for up in r.get("result", []):
            st["offset"] = up["update_id"] + 1
            cq = up.get("callback_query")
            if cq and str(cq.get("data", "")).startswith("c:"):
                tasks.append(asyncio.create_task(handle_claim(client, cq, st)))
            elif cq:
                await api("answerCallbackQuery", callback_query_id=cq["id"])
        save_st(st)
        await asyncio.sleep(1)


async def main():
    first = not os.path.exists(STATE)
    seen = {k.split(":")[0] for k in json.load(open(STATE))} if not first else set()
    st = load_st()
    tasks = []
    end = time.time() + RUN_SECONDS
    sent = 0
    lookups = 0
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        poll = asyncio.create_task(poller(client, st, end, tasks))
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
                    for x in lots:
                        seen.discard(x.slug)
                    continue
                try:
                    lots.sort(key=ton_of)
                    main_lot = lots[0]
                    owner, has_user, plain_name, ent = await owner_of(client, main_lot)
                    if not has_user and lookups < MAX_LOOKUPS:
                        lookups += 1
                        so = await bot_owner(client, "getSendGiftsProBot", main_lot.slug, "Get Gifts")
                        await asyncio.sleep(3)
                        if so:
                            owner += "\n" + so
                    a = attrs(main_lot)
                    mark = "✅ " if has_user else ""
                    text = (f"{mark}🎁 <b>Подарок:</b> <a href=\"https://t.me/nft/{main_lot.slug}\">"
                            f"{html.escape(str(main_lot.title))} #{main_lot.num}</a>\n"
                            f"💰 <b>Цена:</b> {price_text(main_lot)}")
                    if a.get("model"):
                        text += f"\n🎨 <b>Модель:</b> {html.escape(a['model'])}"
                    if a.get("back"):
                        text += f"\n🖼 <b>Фон:</b> {html.escape(a['back'])}"
                    if a.get("pat"):
                        text += f"\n✨ <b>Узор:</b> {html.escape(a['pat'])}"
                    text += f"\n👤 <b>Владелец:</b> {owner}" + status_lines(ent)
                    st["lots"][main_lot.slug] = owner
                    if await send(text, main_lot.slug, topic_of(main_lot, a.get("back", ""), plain_name)):
                        sent += 1
                    await asyncio.sleep(2)
                except Exception as e:
                    print("item error", e)
            json.dump(sorted(seen), open(STATE, "w"))
            first = False
            if time.time() > end:
                break
            await asyncio.sleep(5)
        await poll
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    save_st(st)


asyncio.run(main())
