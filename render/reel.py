#!/usr/bin/env python3
"""A 9:16 Reel with an Italian voiceover from an approved post.

    python render/reel.py drafts/<id>/post.json [out.mp4]

The post needs a "voiceover" list: one spoken line per slide (cover, middle slides, "concreto"; the closing line is
added). A slide is shown while its line is spoken, so the video follows the voice. "concreto" items appear one at a
time; its line may be a list with one sentence per item. Audio: Gemini TTS (GEMINI_API_KEY or ~/.config/gemini/api-key).
Video: the carousel slides re-laid out at 1080x1920 inside Instagram's safe area, slow zoom, push between slides.
"""
import base64, io, json, os, re, subprocess, sys, tempfile, urllib.error, urllib.request, wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import render                                                     # noqa: E402
import images                                                     # noqa: E402
from PIL import Image                                             # noqa: E402

TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
VOICE = os.environ.get("REEL_VOICE", "Charon")
STYLE = ("Leggi in italiano, con voce naturale, calda e sicura, come un giornalista che spiega una notizia a un amico. "
         "Ritmo sostenuto, da reel informativo, ma chiaro e senza enfasi esagerata. Pronuncia AI come 'A I' all'italiana. Testo:\n")
CLOSING = "Segui AI Essenziale: le novità dell'intelligenza artificiale, in italiano."
W, H, FPS, RATE = 1080, 1920, 30, 24000
GAP, PUSH = 0.35, 0.35                                            # seconds after each line; slide transition

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
#stage.say .line { font: 700 calc(80px * var(--k))/1.1 "Space Grotesk"; letter-spacing: -0.02em; text-wrap: balance; }
#stage.say.s-concreto .kicker { background: var(--ink); color: var(--lime); }
#stage.say.s-concreto .line { color: var(--ink); }
</style>"""


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out = []
    for p in parts:                                               # keep very short sentences with the next one
        if out and len(out[-1]) < 22:
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def label(s):
    if s["type"] == "concreto":
        return "In concreto"
    return re.sub(r"[*_]", "", s.get("title", ""))


def tts(text, key):
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
            return base64.b64decode(part["inlineData"]["data"])      # 16-bit mono PCM, 24 kHz
    raise RuntimeError("Gemini TTS returned no audio")


def trim(pcm, threshold=500):
    """Cut leading and trailing silence (the model adds some)."""
    n = len(pcm) // 2
    vals = memoryview(pcm).cast("h")
    start = next((i for i in range(n) if abs(vals[i]) > threshold), 0)
    end = next((i for i in range(n - 1, -1, -1) if abs(vals[i]) > threshold), n - 1)
    pad = int(0.05 * RATE)
    return pcm[max(0, start - pad) * 2:min(n, end + pad) * 2]


def plan(post):
    """[(slide, kind, spoken text)]: the cover speaks its whole line over the cover; every other slide is split into
    sentences, each shown big while it's spoken; the closing slide speaks CLOSING."""
    vo, slides = post.get("voiceover"), post["slides"]
    if not vo or len(vo) != len(slides):
        raise SystemExit(f"voiceover needs {len(slides)} lines (one per slide), found {len(vo or [])}")
    out = []
    for s, line in zip(slides, vo):
        text = " ".join(line) if isinstance(line, list) else line
        if s["type"] == "cover":
            out.append((s, "cover", text))
        else:
            out += [(s, "say", t) for t in sentences(text)]
    out.append(({"type": "cta"}, "cta", CLOSING))
    return out


def main(post_path, out_path=None):
    post = json.load(open(post_path, encoding="utf-8"))
    out_path = out_path or os.path.join(render.ROOT, "media", f"{post['id']}-reel.mp4")
    key = images.api_key()
    if not key:
        raise SystemExit("no Gemini key")
    image, credit = images.cover_image(post)
    segments = plan(post)
    tmp = tempfile.mkdtemp(prefix="aiessenziale-reel-")
    audio, timeline, prev = bytearray(), [], None                 # timeline: per slide, [(image, seconds)]
    b = render.Browser()
    try:
        for i, (s, kind, text) in enumerate(segments, 1):
            speech = trim(tts(text, key))
            secs = len(speech) / 2 / RATE + GAP
            if kind == "cover":
                secs = max(secs, 2.0)
            audio += speech + bytes(2 * (round(secs * RATE) - len(speech) // 2))
            if kind == "say":
                lime = s["type"] == "concreto"
                inner = f'<div class="inner"><div class="kicker">{render.esc(label(s))}</div><p class="line">{render.esc(text)}</p></div>'
                html = REEL_CSS + render.frame(inner, i, len(segments), last=True, image=None if lime else image)
                cls = ("s-concreto" if lime else "s-point") + " reel say" + ("" if lime else " has-pic")
            else:
                inner, c = render.slide_html(s, post["kind"])
                source = post["sources"][0]["name"] if kind == "cover" and post.get("sources") else None
                pic = image if kind == "cover" else None
                html = REEL_CSS + render.frame(inner, i, len(segments), source=source, last=True, image=pic, credit=credit)
                cls = "s-" + c + " reel" + (" has-img" if pic else "")
            im, fit = b.shot(html, cls, (W, H))
            if fit["overflow"]:
                raise SystemExit(f"segment {i}: text does not fit in the Reel layout")
            group = s["type"] if kind == "say" else kind + str(i)
            if group == prev:
                timeline[-1].append((im, secs))                   # same slide: crossfade, no push
            else:
                timeline.append([(im, secs)])
            prev = group
            print(f"{i:2d} {kind:5s} {secs:4.1f} s  {text[:70]}")
    finally:
        b.close()

    wav = os.path.join(tmp, "voice.wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(bytes(audio))

    import imageio_ffmpeg
    ff_exe = imageio_ffmpeg.get_ffmpeg_exe()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    ff = subprocess.Popen([ff_exe, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                           "-preset", "medium", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
                           out_path], stdin=subprocess.PIPE)

    def zoomed(im, z):
        if z <= 1.0005:
            return im
        cw, ch = W / z, H / z
        return im.resize((W, H), Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))

    ease = lambda x: 1 - (1 - x) ** 3
    push, fade, last, total = round(PUSH * FPS), round(0.25 * FPS), None, 0
    for k, segs in enumerate(timeline):
        bounds = [0]
        for _, d in segs:
            bounds.append(bounds[-1] + round(d * FPS))
        frames, amount = bounds[-1], (0.07 if k == 0 else 0.025)
        for f in range(frames):
            j = max(i for i in range(len(segs)) if bounds[i] <= f)
            z = 1 + amount * f / frames
            frame = zoomed(segs[j][0], z)
            if j > 0 and f - bounds[j] < fade:
                frame = Image.blend(zoomed(segs[j - 1][0], z), frame, (f - bounds[j] + 1) / fade)
            if k > 0 and f < push and last is not None:
                x = round(W * (1 - ease((f + 1) / push)))
                canvas = Image.new("RGB", (W, H)); canvas.paste(last, (x - W, 0)); canvas.paste(frame, (x, 0))
                frame = canvas
            ff.stdin.write(frame.tobytes())
            final = frame
        last, total = final, total + frames
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print(f"{out_path} ({total / FPS:.1f} s)")
    return out_path


if __name__ == "__main__":
    main(*sys.argv[1:3])
