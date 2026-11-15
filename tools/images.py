#!/usr/bin/env python3
"""Cover images. A cover gets its picture from, in order:
  1. drafts/<id>/cover.jpg (or .png/.webp): an official image from the company's own announcement, saved by the drafting agent
     (credit it with "image_credit" on the cover slide), or one you add by hand;
  2. media/<id>/cover-ai.jpg: generated earlier from the cover's "image_prompt";
  3. generated now with Gemini from "image_prompt" (house style below), if GEMINI_API_KEY or ~/.config/gemini/api-key exists.
Without any of these the cover stays typographic.

    python3 tools/images.py drafts/<id>/post.json      # generate (or regenerate) the AI cover for one draft
"""
import base64, json, os, sys, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview")
KEY_FILE = os.path.expanduser("~/.config/gemini/api-key")
STYLE = (
    "Editorial cover image for an Italian tech news page. Photorealistic, cinematic 3D render. Dark charcoal environment "
    "with raw concrete textures, one acid-lime (#c8ff2e) accent light, soft volumetric light, shallow depth of field. "
    "One clear subject in the upper half of the frame; the bottom third is dark, calm negative space (text goes there). "
    "No text, no letters, no numbers, no logos, no brand marks, no real people, no readable screens."
)


def api_key():
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"].strip()
    if os.path.isfile(KEY_FILE):
        return open(KEY_FILE).read().strip()
    return None


def generate(subject, key):
    body = {"contents": [{"parts": [{"text": f"{STYLE}\n\nSubject: {subject}"}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "4:5", "imageSize": "2K"}}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini HTTP {e.code}: {e.read().decode()[:300]}") from None
    for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in part:
            return base64.b64decode(part["inlineData"]["data"])
    raise RuntimeError("Gemini returned no image: " + json.dumps(data)[:300])


def cover_image(post, regenerate=False):
    """(path to the cover picture or None, credit text or None)."""
    pid, cover = post["id"], post["slides"][0]
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = os.path.join(ROOT, "drafts", pid, f"cover.{ext}")
        if os.path.isfile(p):
            return p, cover.get("image_credit")
    if not cover.get("image_prompt"):
        return None, None
    ai = os.path.join(ROOT, "media", f"{pid}-cover-ai.jpg")
    if os.path.isfile(ai) and not regenerate:
        return ai, None
    key = api_key()
    if not key:
        print(f"{pid}: no Gemini key, cover stays typographic")
        return None, None
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(generate(cover["image_prompt"], key))).convert("RGB")
    img.thumbnail((1350, 1688))
    os.makedirs(os.path.dirname(ai), exist_ok=True)
    img.save(ai, quality=90)
    return ai, None


if __name__ == "__main__":
    post = json.load(open(sys.argv[1], encoding="utf-8"))
    print(cover_image(post, regenerate=True))
