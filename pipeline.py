#!/usr/bin/env python3
"""The AI Concreta pipeline. GitHub Actions runs it every 10 minutes (and when new drafts are pushed):

  1. poll     read your taps on Telegram: ✅ schedule · ⚡ publish now · ❌ reject · ↩️ undo; commands /coda, /aiuto
  2. render   draw new or changed drafts (drafts/<id>/post.json → media/<id>/NN.jpg)
  3. notify   send each rendered draft to Telegram with the buttons
  4. expire   drafts nobody answered for 36 hours are dropped (news goes stale)
  5. publish  post what's due to Instagram (at most one per run)

    python pipeline.py              # all steps (what the workflow runs)
    python pipeline.py render       # one step: poll, render, notify, expire, publish

Environment: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID (steps 1, 3, 4 are skipped without them); IG_TOKEN, IG_USER_ID;
LIVE=true to really publish (otherwise test mode: it tells you on Telegram what it would have published);
SLOTS (default "12:30,18:30", Europe/Rome); MEDIA_BASE_URL (default https://mdered.github.io/aiconcreta/).

Safety: nothing is published without your ✅/⚡; a post is published once (state/posts.json, committed by the workflow);
one post per run; a post more than 12 hours late is never published, only marked "missed".
"""
import datetime, glob, hashlib, html, json, os, sys, time, traceback, urllib.error, urllib.parse, urllib.request, uuid
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import postspec  # noqa: E402

TZ = ZoneInfo("Europe/Rome")
STATE = os.path.join(ROOT, "state", "posts.json")
TG_STATE = os.path.join(ROOT, "state", "telegram.json")
BASE_URL = os.environ.get("MEDIA_BASE_URL", "https://mdered.github.io/aiconcreta/")
LIVE = os.environ.get("LIVE", "").strip().lower() == "true"
SLOTS = [tuple(map(int, s.split(":"))) for s in (os.environ.get("SLOTS") or "12:30,18:30").split(",") if s.strip()]
TG_TOKEN, TG_CHAT = os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
IG_TOKEN, IG_USER = os.environ.get("IG_TOKEN", ""), os.environ.get("IG_USER_ID", "")
GRAPH = "https://graph.facebook.com/v21.0"
EXPIRE_AFTER = datetime.timedelta(hours=36)
MAX_LATE = datetime.timedelta(hours=12)
ICON = {"news": "📰", "tool": "🛠", "prompt": "💬", "italia": "🇮🇹"}
DAYS = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def load_json(path, default):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def drafts():
    """{id: (path, post, sha256)} for every drafts/<id>/post.json that parses."""
    out = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "drafts", "*", "post.json"))):
        raw = open(p, "rb").read()
        try:
            post = json.loads(raw)
        except ValueError:
            post = {"id": os.path.basename(os.path.dirname(p))}
        out[os.path.basename(os.path.dirname(p))] = (p, post, hashlib.sha256(raw).hexdigest())
    return out


def nice(when_iso):
    d = datetime.datetime.fromisoformat(when_iso).astimezone(TZ)
    return f"{DAYS[d.weekday()]} {d.day}/{d.month} alle {d:%H:%M}"


# ---------------------------------------------------------------- Telegram
def tg(method, **params):
    data = json.dumps(params).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/{method}", data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)["result"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Telegram {method}: {e.read().decode()[:300]}") from None


def tg_album(paths):
    """Sends the slides as one album; returns the message ids."""
    boundary = uuid.uuid4().hex
    media = [{"type": "photo", "media": f"attach://f{i}"} for i in range(len(paths))]
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{TG_CHAT}\r\n'.encode(),
             f'--{boundary}\r\nContent-Disposition: form-data; name="media"\r\n\r\n{json.dumps(media)}\r\n'.encode()]
    for i, p in enumerate(paths):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="f{i}"; filename="{i:02d}.jpg"\r\n'
                     f'Content-Type: image/jpeg\r\n\r\n'.encode() + open(p, "rb").read() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendMediaGroup", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return [m["message_id"] for m in json.load(r)["result"]]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Telegram sendMediaGroup: {e.read().decode()[:300]}") from None


def say(text):
    if TG_TOKEN and TG_CHAT:
        try:
            tg("sendMessage", chat_id=TG_CHAT, text=text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            print(f"telegram: {e}")


def keyboard(status, pid):
    if status == "sent":
        return {"inline_keyboard": [[{"text": "✅ Programma", "callback_data": f"ok|{pid}"},
                                     {"text": "⚡ Appena possibile", "callback_data": f"now|{pid}"}],
                                    [{"text": "❌ Scarta", "callback_data": f"no|{pid}"}]]}
    if status in ("scheduled", "rejected"):
        return {"inline_keyboard": [[{"text": "↩️ Annulla", "callback_data": f"undo|{pid}"}]]}
    return {"inline_keyboard": []}


def preview(post, entry):
    """The text under the album: kind, cover title, the caption as it will be published, sources, current status."""
    e = html.escape
    srcs = "\n".join(f'• <a href="{e(s["url"])}">{e(s["name"])}</a>' for s in post.get("sources") or []) or "nessuna (contenuto evergreen)"
    cap = postspec.full_caption(post)
    if len(cap) > 2600:
        cap = cap[:2600] + "…"
    status = {"sent": "⏳ In attesa della tua scelta (scade dopo 36 ore).\nDopo il tocco il messaggio si aggiorna entro 10–20 minuti: basta un tocco.",
              "scheduled": f"✅ Programmato: {nice(entry['when'])}" if entry.get("when") else "✅ Programmato",
              "rejected": "❌ Scartato", "expired": "⌛ Scaduto (nessuna risposta in 36 ore)",
              "published": "📣 Pubblicato", "test": "🧪 Pubblicato in modalità test (non davvero)",
              "missed": "⚠️ Non pubblicato: troppo in ritardo", "failed": "⚠️ Pubblicazione fallita",
              "superseded": "♻️ Sostituito da una versione aggiornata (qui sotto)"}.get(entry["status"], entry["status"])
    return (f"{ICON.get(post['kind'], '')} <b>{postspec.KINDS[post['kind']].upper()}</b> · <code>{e(post['id'])}</code>\n\n"
            f"<b>{e(postspec.cover_title(post))}</b>\n\n<b>Didascalia</b>\n{e(cap)}\n\n<b>Fonti</b>\n{srcs}\n\n{status}")


def refresh(pid, entry, post):
    """Updates the Telegram message of a draft to its current status and buttons."""
    if not (TG_TOKEN and entry.get("msg_id")):
        return
    try:
        tg("editMessageText", chat_id=TG_CHAT, message_id=entry["msg_id"], text=preview(post, entry), parse_mode="HTML",
           disable_web_page_preview=True, reply_markup=keyboard(entry["status"], pid))
    except RuntimeError as e:
        if "not modified" not in str(e):
            print(f"telegram edit {pid}: {e}")


# ---------------------------------------------------------------- scheduling
def next_slot(state, after=None):
    taken = {e["when"] for e in state.values() if e.get("status") in ("scheduled", "published", "test") and e.get("when")}
    start = (after or now()) + datetime.timedelta(minutes=15)
    day = start.astimezone(TZ).date()
    for d in range(30):
        for h, m in sorted(SLOTS):
            t = datetime.datetime.combine(day + datetime.timedelta(days=d), datetime.time(h, m), TZ)
            if t >= start and t.isoformat() not in taken:
                return t.isoformat()
    raise RuntimeError("no free slot in the next 30 days")


# ---------------------------------------------------------------- steps
def step_poll(state, posts):
    if not (TG_TOKEN and TG_CHAT):
        print("poll: no Telegram secrets, skipped")
        return
    tgs = load_json(TG_STATE, {"offset": 0})
    updates = tg("getUpdates", offset=tgs["offset"], timeout=0, allowed_updates=["callback_query", "message"])
    for u in updates:
        tgs["offset"] = u["update_id"] + 1
        try:
            handle_update(u, state, posts)
        except Exception:
            print(f"update {u['update_id']} failed:\n{traceback.format_exc()}")
        save_json(TG_STATE, tgs)                                  # a tap is handled once, even if a later one fails


def handle_update(u, state, posts):
        if "callback_query" in u:
            q = u["callback_query"]
            if str(q.get("message", {}).get("chat", {}).get("id")) != str(TG_CHAT):
                return                                            # only you can approve
            action, _, pid = q.get("data", "").partition("|")
            entry, answer = state.get(pid), "Fatto"
            post = posts.get(pid, (None, None, None))[1]
            if not entry or not post:
                answer = "Bozza non trovata"
            elif action in ("ok", "now") and entry["status"] == "sent":
                when = next_slot(state) if action == "ok" else now().isoformat(timespec="seconds")
                entry.update(status="scheduled", when=when, decided_at=now().isoformat(timespec="seconds"))
                answer = f"Programmato: {nice(entry['when'])}" if action == "ok" else "Lo pubblico al prossimo giro (entro ~20 min)"
            elif action == "no" and entry["status"] == "sent":
                entry["status"], entry["decided_at"] = "rejected", now().isoformat(timespec="seconds")
                answer = "Scartato"
            elif action == "undo" and entry["status"] in ("scheduled", "rejected"):
                entry["status"] = "sent"; entry.pop("when", None)
                answer = "Annullato: scegli di nuovo"
            else:
                answer = f"Già gestito ({entry['status']})"
            try:
                tg("answerCallbackQuery", callback_query_id=q["id"], text=answer)
            except RuntimeError:
                pass                                              # taps older than a few minutes can't be answered
            if entry and post:
                refresh(pid, entry, post)
            print(f"tap {action} {pid}: {answer}")
        elif "message" in u and str(u["message"].get("chat", {}).get("id")) == str(TG_CHAT):
            cmd = (u["message"].get("text") or "").strip().split()[0:1]
            if cmd and cmd[0] in ("/coda", "/queue"):
                rows = sorted((e["when"], pid) for pid, e in state.items() if e.get("status") == "scheduled")
                pending = sum(e.get("status") == "sent" for e in state.values())
                say("<b>In coda</b>\n" + ("\n".join(f"• {nice(w)}: <code>{html.escape(p)}</code>" for w, p in rows) or "niente")
                    + f"\n\nIn attesa di una tua scelta: {pending}\nModalità: {'LIVE' if LIVE else 'TEST (non pubblica davvero)'}")
            elif cmd:
                say("Tocca i pulsanti sotto ogni bozza.\n✅ Programma: al prossimo orario libero "
                    f"({', '.join(f'{h}:{m:02d}' for h, m in SLOTS)})\n⚡ Appena possibile: entro ~20 minuti\n❌ Scarta\n↩️ Annulla\n\n/coda: cosa è programmato")


def step_render(state, posts):
    import render  # needs Chrome + pillow + websocket-client; imported only when there's something to draw
    for pid, (path, post, sha) in posts.items():
        e = state.get(pid)
        if e and e["status"] not in ("new", "rendered", "sent", "render_failed"):
            continue
        if e and e.get("hash") == sha and not (e["status"] == "render_failed" and e.get("attempts", 0) < 3):
            continue                                              # unchanged (a failed render is retried up to 3 times)
        if not e:
            try:
                created = datetime.datetime.fromisoformat(post.get("created", ""))
            except ValueError:
                created = now()
            if now() - created > EXPIRE_AFTER:
                state[pid] = {"status": "expired", "hash": sha, "note": "too old when first seen"}
                continue
        old = dict(e) if e else None
        try:
            files = render.render_post(path)
        except (Exception, SystemExit) as err:
            tries = (old or {}).get("attempts", 0) + 1 if (old or {}).get("hash") == sha else 1
            state[pid] = {**(old or {}), "status": "render_failed", "hash": sha, "error": str(err)[:800], "attempts": tries}
            if tries >= 3:
                say(f"⚠️ Non riesco a disegnare la bozza <code>{html.escape(pid)}</code>:\n<pre>{html.escape(str(err)[:800])}</pre>")
            print(f"render {pid}: FAILED {err}")
            continue
        if old and old.get("status") == "sent" and old.get("msg_id"):               # an edited draft: retire the old message
            refresh(pid, {**old, "status": "superseded"}, post)
        state[pid] = {"status": "rendered", "hash": sha, "created": post["created"], "kind": post["kind"],
                      "images": [os.path.relpath(f, ROOT) for f in files]}
        print(f"render {pid}: {len(files)} slides")


def step_notify(state, posts):
    if not (TG_TOKEN and TG_CHAT):
        print("notify: no Telegram secrets, skipped")
        return
    for pid, e in sorted(state.items()):
        if e["status"] != "rendered" or pid not in posts:
            continue
        post = posts[pid][1]
        e["album"] = tg_album([os.path.join(ROOT, p) for p in e["images"]])
        e["status"], e["sent_at"] = "sent", now().isoformat(timespec="seconds")
        e["msg_id"] = tg("sendMessage", chat_id=TG_CHAT, text=preview(post, e), parse_mode="HTML",
                         disable_web_page_preview=True, reply_markup=keyboard("sent", pid))["message_id"]
        print(f"notify {pid}")


def step_expire(state, posts):
    for pid, e in state.items():
        if e["status"] == "sent" and now() - datetime.datetime.fromisoformat(e["created"]) > EXPIRE_AFTER:
            e["status"] = "expired"
            if pid in posts:
                refresh(pid, e, posts[pid][1])
            print(f"expire {pid}")


def graph(method, path, **params):
    params["access_token"] = IG_TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = f"{GRAPH}/{path}"
    req = urllib.request.Request(url, data=data, method="POST") if method == "POST" else urllib.request.Request(f"{url}?{data.decode()}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        err = json.loads(e.read() or b"{}").get("error", {})
        raise RuntimeError(f"{method} {path}: {err.get('message', e.code)}") from None


def wait_ready(container):
    for _ in range(60):
        status = graph("GET", container, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {container}: {status}")
        time.sleep(5)
    raise RuntimeError(f"container {container}: not ready after 5 minutes")


def online(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
            return r.status == 200 and "jpeg" in r.headers.get("Content-Type", "")
    except Exception:
        return False


def instagram(urls, caption):
    children = []
    for u in urls:
        c = graph("POST", f"{IG_USER}/media", image_url=u, is_carousel_item="true")["id"]
        wait_ready(c); children.append(c)
    parent = graph("POST", f"{IG_USER}/media", media_type="CAROUSEL", children=",".join(children), caption=caption)["id"]
    wait_ready(parent)
    media = graph("POST", f"{IG_USER}/media_publish", creation_id=parent)["id"]
    try:
        link = graph("GET", media, fields="permalink").get("permalink")
    except RuntimeError:
        link = None
    return media, link


def step_publish(state, posts):
    due = sorted((e["when"], pid) for pid, e in state.items()
                 if e["status"] == "scheduled" and e.get("when") and datetime.datetime.fromisoformat(e["when"]) <= now())
    for when, pid in due:
        e, post = state[pid], posts.get(pid, (None, None, None))[1]
        if not post:
            e["status"], e["error"] = "failed", "draft file is gone"
            continue
        if now() - datetime.datetime.fromisoformat(when) > MAX_LATE:
            e["status"] = "missed"; refresh(pid, e, post)
            say(f"⚠️ Non pubblicato perché in ritardo di oltre 12 ore: <code>{html.escape(pid)}</code>")
            continue
        urls = [BASE_URL + p for p in e["images"]]
        if not all(online(u) for u in urls):
            print(f"publish {pid}: images not online yet at {BASE_URL}, retrying next run")
            return
        caption = postspec.full_caption(post)
        if not LIVE or not (IG_TOKEN and IG_USER):
            e["status"], e["published_at"] = "test", now().isoformat(timespec="seconds")
            refresh(pid, e, post)
            say(f"🧪 <b>Modalità test</b>: ora avrei pubblicato <code>{html.escape(pid)}</code> ({len(urls)} slide).")
            print(f"publish {pid}: TEST MODE, not published")
            return
        try:
            e["media_id"], e["permalink"] = instagram(urls, caption)
            e["status"], e["published_at"] = "published", now().isoformat(timespec="seconds")
            refresh(pid, e, post)
            say(f"📣 Pubblicato: <b>{html.escape(postspec.cover_title(post))}</b>\n{e.get('permalink') or ''}")
            print(f"publish {pid}: PUBLISHED {e['media_id']}")
        except Exception as err:
            e["attempts"] = e.get("attempts", 0) + 1
            e["error"] = str(err)[:500]
            if e["attempts"] >= 3:
                e["status"] = "failed"; refresh(pid, e, post)
                say(f"⚠️ Pubblicazione fallita 3 volte per <code>{html.escape(pid)}</code>:\n<pre>{html.escape(str(err)[:500])}</pre>")
            print(f"publish {pid}: FAILED ({e['attempts']}) {err}")
        return                                                    # one post per run


STEPS = {"poll": step_poll, "render": step_render, "notify": step_notify, "expire": step_expire, "publish": step_publish}


def main():
    names = sys.argv[1:] or list(STEPS)
    state, posts = load_json(STATE, {}), drafts()
    for e in state.values():                                      # repair: "scheduled" without a time goes back to your choice
        if e.get("status") == "scheduled" and not e.get("when"):
            e["status"] = "sent"
    print(f"{'LIVE' if LIVE else 'TEST MODE'} · {now().astimezone(TZ):%Y-%m-%d %H:%M} Rome · {len(posts)} drafts")
    failed = False
    sys.path.insert(0, os.path.join(ROOT, "render"))
    for n in names:
        try:
            STEPS[n](state, posts)
        except Exception:
            failed = True
            print(f"step {n} failed:\n{traceback.format_exc()}")
        save_json(STATE, state)                                   # after every step, so a later failure loses nothing
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
