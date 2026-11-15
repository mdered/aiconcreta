#!/usr/bin/env python3
"""Draws a post's slides as JPEGs (1080 × 1350) with headless Chrome.

    python render/render.py drafts/<id>/post.json [out_dir]     # default out_dir: media/<id>/
    python render/render.py profile [out.png]                   # the profile picture (1080 × 1080)

Text that doesn't fit is shrunk (to 72%); if it still overflows, the slide is reported and the exit code is 1,
so nothing cut off is ever published. Needs Chrome (CHROME=/path, default: macOS app or `google-chrome`) and
`pip install pillow websocket-client`.
"""
import base64, html, io, json, os, re, shutil, socket, subprocess, sys, tempfile, time, urllib.request

import websocket
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import postspec  # noqa: E402

MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME = os.environ.get("CHROME") or (MAC_CHROME if os.path.exists(MAC_CHROME) else shutil.which("google-chrome") or "chromium")
FEED = (1080, 1350)
HANDLE = "@aiessenziale"


def esc(s):
    """HTML-escape, then *words* → lime accent."""
    return re.sub(r"\*(.+?)\*", r"<em>\1</em>", html.escape(s, quote=False))


class Browser:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="aiessenziale-chrome-")
        with socket.socket() as sk:
            sk.bind(("127.0.0.1", 0)); port = sk.getsockname()[1]
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1", "--allow-file-access-from-files",
             "--no-sandbox", "--disable-gpu", "--run-all-compositor-stages-before-draw", "--remote-allow-origins=*",
             f"--remote-debugging-port={port}", f"--user-data-dir={self.tmp}", "--window-size=1080,1350", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        page = None
        for _ in range(150):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                page = [t for t in tabs if t["type"] == "page"][0]
                break
            except Exception:
                time.sleep(.1)
        if not page:
            raise RuntimeError(f"Chrome did not start ({CHROME})")
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], max_size=None)
        self.n = 0
        self.cmd("Page.enable")
        self.cmd("Page.navigate", url="file://" + os.path.join(HERE, "slide.html"))
        for _ in range(300):
            time.sleep(.1)
            try:
                if self.js("window.READY === true"):
                    return
            except RuntimeError:
                pass
        raise RuntimeError("slide.html did not load")

    def cmd(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m["result"]

    def js(self, expr):
        r = self.cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:600])
        return r["result"].get("value")

    def shot(self, markup, cls, size):
        w, h = size
        self.cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
        fit = self.js(f"show({json.dumps(markup)}, {json.dumps(cls)}, {w}, {h})")
        im = Image.open(io.BytesIO(base64.b64decode(self.cmd("Page.captureScreenshot", format="png")["data"]))).convert("RGB")
        return im, fit

    def close(self):
        self.ws.close(); self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill(); self.proc.wait()
        shutil.rmtree(self.tmp, ignore_errors=True)               # Chrome may still be flushing its profile: never fail here


# ---------------------------------------------------------------- slides
def frame(inner, page, total, kind_label=None, source=None, last=False, image=None, credit=None):
    top = f'<div class="top"><div class="brand"><div class="slab"><span>AI</span></div>ESSENZIALE</div><div class="pg">{page}/{total}</div></div>'
    left = esc(f"Fonte: {source}") if source else HANDLE
    right = "" if last else '<span class="next">Scorri <i>→</i></span>'
    pic = ""
    if image:
        tag = esc(f"Immagine: {credit}") if credit else "Immagine generata con AI"
        pic = f'<div class="pic"><img src="file://{image}"><div class="fade"></div><span class="credit">{tag}</span></div>'
    return (f'<div class="bg"></div>{pic}<div class="grain"></div>{top}<div class="content">{inner}</div>'
            f'<div class="rule"></div><div class="bottom"><span>{left}</span>{right}</div>')


def slide_html(s, kind):
    t = s["type"]
    if t == "cover":
        sub = f'<p class="sub">{esc(s["sub"])}</p>' if s.get("sub") else ""
        return f'<div class="inner"><div class="kicker">{postspec.KINDS[kind]}</div><h1>{esc(s["title"])}</h1>{sub}</div>', "cover"
    if t == "point":
        return f'<div class="inner"><div class="num">{s["_n"]:02d}</div><h2>{esc(s["title"])}</h2><p class="body">{esc(s["body"])}</p></div>', "point"
    if t == "list":
        items = "".join(f'<div class="item"><span>{esc(i)}</span></div>' for i in s["items"])
        return f'<div class="inner"><h2>{esc(s["title"])}</h2><div class="items">{items}</div></div>', "list"
    if t == "prompt":
        note = f'<p class="prompt-tag">{esc(s["note"])}</p>' if s.get("note") else '<p class="prompt-tag">Copialo e incollalo nel tuo chatbot.</p>'
        return (f'<div class="inner"><div class="label">Il prompt</div><h2>{esc(s["title"])}</h2>'
                f'<div class="prompt">{html.escape(s["prompt"], quote=False)}</div>{note}</div>'), "prompt"
    if t == "concreto":
        items = "".join(f'<div class="c-item"><span>{esc(i)}</span></div>' for i in s["items"])
        return f'<div class="inner"><div class="concreto-title">In concreto.</div><div class="c-items">{items}</div></div>', "concreto"
    if t == "cta":
        return ('<div class="inner cta"><div class="slab"><span>AI</span></div><h2>Segui <em>@aiessenziale</em></h2>'
                '<p class="sub">L\'essenziale dell\'intelligenza artificiale. Ogni giorno, in italiano.</p>'
                '<div class="actions"><span><i>↗</i>Condividi</span><span><i>■</i>Salva</span><span><i>+</i>Segui</span></div></div>'), "cta"
    raise ValueError(t)


def render_post(post_path, out_dir=None, with_images=True):
    post = json.load(open(post_path, encoding="utf-8"))
    problems = postspec.check(post, os.path.basename(os.path.dirname(os.path.abspath(post_path))))
    if problems:
        raise SystemExit("invalid post:\n  " + "\n  ".join(problems))
    out_dir = out_dir or os.path.join(ROOT, "media", post["id"])
    slides = [dict(s) for s in post["slides"]] + [{"type": "cta"}]
    n = 0
    for s in slides:
        if s["type"] == "point":
            n += 1; s["_n"] = n
    image, credit = (None, None)
    if with_images:
        import images
        try:
            image, credit = images.cover_image(post)
        except Exception as e:                                    # no picture is better than no post
            print(f"{post['id']}: cover image failed ({e}), typographic cover")
    tmp = out_dir + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    bad, b = [], Browser()
    try:
        for i, s in enumerate(slides, 1):
            inner, cls = slide_html(s, post["kind"])
            source = post["sources"][0]["name"] if s["type"] == "cover" and post.get("sources") else None
            pic = image if s["type"] == "cover" else None
            im, fit = b.shot(frame(inner, i, len(slides), source=source, last=i == len(slides), image=pic, credit=credit),
                             "s-" + cls + (" has-img" if pic else ""), FEED)
            im.save(os.path.join(tmp, f"{i:02d}.jpg"), quality=92, optimize=True)
            if fit["overflow"]:
                bad.append(f"slide {i} ({s['type']}): text does not fit")
    finally:
        b.close()
    if bad:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit(f"{post['id']}:\n  " + "\n  ".join(bad))
    shutil.rmtree(out_dir, ignore_errors=True); os.rename(tmp, out_dir)
    return sorted(os.path.join(out_dir, f) for f in os.listdir(out_dir))


def render_profile(path):
    b = Browser()
    try:
        im, _ = b.shot('<div class="slab"><span>AI</span></div>', "s-profile", (1080, 1080))
        im.save(path)
    finally:
        b.close()
    return path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == "profile":
        print(render_profile(sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "profile.png")))
    else:
        for f in render_post(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None):
            print(f)
