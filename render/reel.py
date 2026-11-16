#!/usr/bin/env python3
"""A 9:16 Reel with an Italian voiceover from an approved post.

    python render/reel.py drafts/<id>/post.json [out.mp4]

The post needs a "voiceover" list: one spoken line per slide (the closing line is added). The cover speaks its line over
the cover; every other line is split into sentences, each shown big while it's spoken: words appear one at a time in
step with the voice, the word being spoken is lime, a progress bar runs along the top.
Voice: Gemini TTS for now (GEMINI_API_KEY or ~/.config/gemini/api-key); `speak()` is the one place to change it.
"""
import base64, json, os, re, subprocess, sys, tempfile, urllib.error, urllib.request, wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import render                                                     # noqa: E402
import images                                                     # noqa: E402
from PIL import Image, ImageDraw                                  # noqa: E402

TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
VOICE = os.environ.get("REEL_VOICE", "Charon")
STYLE = ("Leggi in italiano, con voce naturale, calda e sicura, come un giornalista che spiega una notizia a un amico. "
         "Ritmo sostenuto, da reel informativo, ma chiaro e senza enfasi esagerata. Testo:\n")
CLOSING = "Segui AI Essenziale: le novità dell'intelligenza artificiale, in italiano."
SAY_AS = [(r"\bAI Essenziale\b", "Ei-Ai Essenziale")]             # how the voice says the name (screen text unchanged)
W, H, FPS, RATE = 1080, 1920, 30, 24000
GAP, PUSH, POP, OUT = 0.3, 0.35, 0.16, 0.12                       # pause after a line; slide push; word pop; text out
LIME = (200, 255, 46)

REEL_CSS = """<style>
#stage.reel .pg, #stage.reel .bottom .next { display: none; }
#stage.reel .top { top: 150px; }
#stage.reel .content { top: 300px; bottom: 560px; }
#stage.reel .rule { bottom: 500px; }
#stage.reel .bottom { bottom: 440px; }
#stage.reel .pic { height: 1180px; }
#stage.reel .pic .credit { top: 232px; }
#stage.reel.has-img .content { top: 860px; bottom: 540px; }
#stage.say .pic { height: 1920px; opacity: .30; }
#stage.say .pic .credit { opacity: 0; }
#stage.say .content { justify-content: center; }
#stage.say .kicker { margin-bottom: calc(44px * var(--k)); }
#stage.say .line { font: 700 calc(84px * var(--k))/1.1 "Space Grotesk"; letter-spacing: -0.02em; text-wrap: balance; }
#stage.say.s-concreto .kicker { background: var(--ink); color: var(--lime); }
#stage.say.s-concreto .line { color: var(--ink); }
</style>"""

WRAP_JS = """(sel => { const el = document.querySelector(sel); if (!el) return [];
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), nodes = [];
  while (w.nextNode()) nodes.push(w.currentNode);
  for (const n of nodes) { const f = document.createDocumentFragment();
    for (const p of n.textContent.split(/(\\s+)/)) {
      if (!p || /^\\s+$/.test(p)) { f.appendChild(document.createTextNode(p)); continue; }
      const s = document.createElement('span'); s.className = 'w'; s.textContent = p; f.appendChild(s); }
    n.parentNode.replaceChild(f, n); }
  return [...el.querySelectorAll('.w')].map(s => { const r = s.getBoundingClientRect();
    return [r.left, r.top, r.right, r.bottom, s.textContent.length]; }); })(%s)"""


# ---------------------------------------------------------------- voice
def speak(text, key):
    """16-bit mono PCM at RATE for one line."""
    for pattern, said in SAY_AS:
        text = re.sub(pattern, said, text)
    body = {"contents": [{"parts": [{"text": STYLE + text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{TTS_MODEL}:generateContent",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini TTS HTTP {e.code}: {e.read().decode()[:300]}") from None
    for part in data["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            return trim(base64.b64decode(part["inlineData"]["data"]))
    raise RuntimeError("Gemini TTS returned no audio")


def trim(pcm, threshold=500):
    n = len(pcm) // 2
    vals = memoryview(pcm).cast("h")
    start = next((i for i in range(n) if abs(vals[i]) > threshold), 0)
    end = next((i for i in range(n - 1, -1, -1) if abs(vals[i]) > threshold), n - 1)
    pad = int(0.05 * RATE)
    return pcm[max(0, start - pad) * 2:min(n, end + pad) * 2]


# ---------------------------------------------------------------- script
def sentences(text):
    out = []
    for p in re.split(r"(?<=[.!?])\s+", text.strip()):
        if out and len(out[-1]) < 22:                             # keep very short sentences with the next one
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def label(s):
    return "In concreto" if s["type"] == "concreto" else re.sub(r"[*_]", "", s.get("title", ""))


def plan(post):
    """[(slide, kind, spoken text)]"""
    vo, slides = post.get("voiceover"), post["slides"]
    if not vo or len(vo) != len(slides):
        raise SystemExit(f"voiceover needs {len(slides)} lines (one per slide), found {len(vo or [])}")
    out = []
    for s, line in zip(slides, vo):
        text = " ".join(line) if isinstance(line, list) else line
        out += [(s, "cover", text)] if s["type"] == "cover" else [(s, "say", t) for t in sentences(text)]
    out.append(({"type": "cta"}, "cta", CLOSING))
    return out


# ---------------------------------------------------------------- pictures
def capture(b, html, cls, words_sel=None, highlight=True):
    """Full frame, the frame with the animated words hidden, the frame with them lime, and the word boxes."""
    b.cmd("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
    fit = b.js(f"show({json.dumps(html)}, {json.dumps(cls)}, {W}, {H})")
    if fit["overflow"]:
        raise SystemExit("text does not fit in the Reel layout")
    shot = lambda: Image.open(__import__("io").BytesIO(base64.b64decode(
        b.cmd("Page.captureScreenshot", format="png")["data"]))).convert("RGB")
    boxes = b.js(WRAP_JS % json.dumps(words_sel)) if words_sel else []
    full = shot()
    if not boxes:
        return full, full, full, []
    b.js("document.querySelectorAll('.w').forEach(s => s.style.opacity = 0)")
    empty = shot()
    lit = full
    if highlight:
        b.js("document.querySelectorAll('.w').forEach(s => { s.style.opacity = 1; s.style.color = '#c8ff2e'; })")
        lit = shot()
    return full, empty, lit, boxes


def word_times(boxes, speech_secs, fast=False):
    """When each word starts: spread over the speech by length (the voice gives no timestamps)."""
    if fast:                                                      # the cover title: a quick cascade
        return [0.08 * i for i in range(len(boxes))]
    weights = [max(2, b[4]) + 1.5 for b in boxes]
    total, t, out = sum(weights), 0.0, []
    for w in weights:
        out.append(0.04 + t / total * speech_secs * 0.96)
        t += w
    return out


def compose(seg, t):
    """The frame of one segment at t seconds."""
    full, empty, lit, boxes, times = seg["full"], seg["empty"], seg["lit"], seg["boxes"], seg["times"]
    if not boxes:
        return full
    if t >= times[-1] + POP and not seg["highlight"]:
        return full
    frame = empty.copy()
    for i, (x0, y0, x1, y1, _) in enumerate(boxes):
        p = (t - times[i]) / POP
        if p <= 0:
            break
        p = min(1.0, p)
        speaking = seg["highlight"] and times[i] <= t < (times[i + 1] if i + 1 < len(times) else seg["speech"])
        src = lit if speaking else full
        box = (int(x0) - 6, int(y0) - 4, int(x1) + 6, int(y1) + 8)
        piece = src.crop(box)
        e = 1 - (1 - p) ** 3
        dy = round((1 - e) * 26)
        if p < 1:
            mask = Image.new("L", piece.size, round(255 * e))
            frame.paste(piece, (box[0], box[1] + dy), mask)
        else:
            frame.paste(piece, box[:2])
    return frame


def zoomed(im, z):
    if z <= 1.0005:
        return im
    cw, ch = W / z, H / z
    return im.resize((W, H), Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))


# ---------------------------------------------------------------- main
def main(post_path, out_path=None):
    post = json.load(open(post_path, encoding="utf-8"))
    out_path = out_path or os.path.join(render.ROOT, "media", f"{post['id']}-reel.mp4")
    key = images.api_key()
    if not key:
        raise SystemExit("no Gemini key")
    image, credit = images.cover_image(post)
    segments = plan(post)
    tmp = tempfile.mkdtemp(prefix="aiessenziale-reel-")
    audio, groups, prev = bytearray(), [], None
    b = render.Browser()
    try:
        for i, (s, kind, text) in enumerate(segments, 1):
            speech = speak(text, key)
            sp = len(speech) / 2 / RATE
            secs = max(sp + GAP, 2.2 if kind == "cover" else 0)
            audio += speech + bytes(2 * (round(secs * RATE) - len(speech) // 2))
            if kind == "say":
                lime = s["type"] == "concreto"
                inner = (f'<div class="inner"><div class="kicker">{render.esc(label(s))}</div>'
                         f'<p class="line">{render.esc(text)}</p></div>')
                html = REEL_CSS + render.frame(inner, i, len(segments), last=True, image=None if lime else image)
                cls = ("s-concreto" if lime else "s-point") + " reel say"
                full, empty, lit, boxes = capture(b, html, cls, ".line", highlight=not lime)
                times = word_times(boxes, sp)
                hl = not lime
            else:
                inner, c = render.slide_html(s, post["kind"])
                source = post["sources"][0]["name"] if kind == "cover" and post.get("sources") else None
                pic = image if kind == "cover" else None
                html = REEL_CSS + render.frame(inner, i, len(segments), source=source, last=True, image=pic, credit=credit)
                cls = "s-" + c + " reel" + (" has-img" if pic else "")
                full, empty, lit, boxes = capture(b, html, cls, "h1, .cta h2" if kind != "cta" else ".cta h2", highlight=False)
                times = word_times(boxes, sp, fast=True)
                hl = False
            seg = dict(full=full, empty=empty, lit=lit, boxes=boxes, times=times, secs=secs, speech=sp, highlight=hl)
            group = s["type"] if kind == "say" else kind + str(i)
            if group == prev:
                groups[-1].append(seg)
            else:
                groups.append([seg])
            prev = group
            print(f"{i:2d} {kind:5s} {secs:4.1f} s  {len(boxes):2d} words  {text[:60]}")
    finally:
        b.close()

    wav = os.path.join(tmp, "voice.wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(bytes(audio))

    import imageio_ffmpeg
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    ff = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                           "-crf", "23", "-preset", "medium", "-c:a", "aac", "-b:a", "160k", "-shortest",
                           "-movflags", "+faststart", out_path], stdin=subprocess.PIPE)
    total_frames = sum(round(sg["secs"] * FPS) for g in groups for sg in g)
    ease = lambda x: 1 - (1 - x) ** 3
    push, out_n, n, last = round(PUSH * FPS), round(OUT * FPS), 0, None
    for k, group in enumerate(groups):
        frames = sum(round(sg["secs"] * FPS) for sg in group)
        amount, f0 = (0.08 if k == 0 else 0.03), 0
        for j, sg in enumerate(group):
            count = round(sg["secs"] * FPS)
            for f in range(count):
                z = 1 + amount * (f0 + f) / frames
                frame = zoomed(compose(sg, f / FPS), z)
                if j > 0 and f < out_n:                           # previous sentence fades out quickly
                    frame = Image.blend(last, frame, (f + 1) / (out_n + 1))
                if k > 0 and j == 0 and f < push and last is not None:   # new slide pushes the old one left
                    x = round(W * (1 - ease((f + 1) / push)))
                    canvas = Image.new("RGB", (W, H)); canvas.paste(last, (x - W, 0)); canvas.paste(frame, (x, 0))
                    frame = canvas
                bar = ImageDraw.Draw(frame)
                bar.rectangle((0, 0, round(W * (n + 1) / total_frames), 9), fill=LIME)
                ff.stdin.write(frame.tobytes())
                n += 1
                if f == count - 1:
                    last = frame
            f0 += count
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print(f"{out_path} ({n / FPS:.1f} s)")
    return out_path


if __name__ == "__main__":
    main(*sys.argv[1:3])
