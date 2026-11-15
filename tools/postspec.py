"""The post format (drafts/<id>/post.json) and its checks. Used by validate.py, render.py and pipeline.py.

{
  "id": "2026-11-16-gemini-in-gmail",          # YYYY-MM-DD-slug, lowercase, at most 48 characters, same as the folder
  "kind": "news",                               # news | tool | prompt | italia
  "created": "2026-11-16T06:40:00+01:00",
  "story_key": "https://blog.google/...",       # the primary source URL: how repeats are detected
                                                # (evergreen prompt posts: "evergreen:<slug>", sources may be [])
  "sources": [{"name": "Google", "url": "https://blog.google/..."}],
  "slides": [                                   # 3-7 slides; the closing "follow" slide is added automatically
    {"type": "cover", "title": "Gemini ora *scrive le mail* al posto tuo", "sub": "optional line under the title",
     "image_prompt": "English scene description for the AI cover (see BRAND.md)",   # optional
     "image_credit": "Google"},                 # only with drafts/<id>/cover.jpg from the company's own announcement
    {"type": "point", "title": "...", "body": "..."},
    {"type": "list", "title": "...", "items": ["...", "..."]},
    {"type": "prompt", "title": "...", "prompt": "...", "note": "optional"},
    {"type": "concreto", "items": ["...", "..."]}          # exactly one, last
  ],
  "caption": "Hook line\\n\\nShort text...\\n\\nQuestion for the comments?",
  "hashtags": ["#intelligenzaartificiale", "#ai", "..."]
}
Accent words in titles: wrap them in *asterisks* (shown in lime).
"""
import datetime, re

KINDS = {"news": "Novità", "tool": "Tool", "prompt": "Prompt", "italia": "Italia"}
LIMITS = {  # characters
    "cover.title": 80, "cover.sub": 140, "cover.image_prompt": 500, "cover.image_credit": 40, "point.title": 70, "point.body": 300, "list.title": 70, "list.item": 110,
    "prompt.title": 70, "prompt.prompt": 420, "prompt.note": 120, "concreto.item": 120, "caption": 1600,
}
AI_NOTE = "Contenuto preparato con l'aiuto dell'AI e verificato dalla redazione."
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")      # fine in captions, not on slides
BANNED = ("rivoluzionari", "incredibil", "pazzesc", "game changer", "game-changer", "sconvolgent", "non crederai", "cambierà tutto")


def check(post, folder_name=None):
    """Returns a list of problems (empty = valid)."""
    p = []
    pid = post.get("id", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[a-z0-9]+(-[a-z0-9]+)*", pid) or len(pid) > 48:
        p.append(f"id '{pid}': must be YYYY-MM-DD-slug, lowercase, at most 48 characters")
    if folder_name and pid != folder_name:
        p.append(f"id '{pid}' differs from the folder name '{folder_name}'")
    if post.get("kind") not in KINDS:
        p.append(f"kind must be one of {', '.join(KINDS)}")
    try:
        datetime.datetime.fromisoformat(post.get("created", ""))
    except ValueError:
        p.append("created: ISO date-time with timezone required")
    evergreen = post.get("kind") == "prompt" and str(post.get("story_key", "")).startswith("evergreen:")
    if not evergreen and not str(post.get("story_key", "")).startswith("http"):
        p.append("story_key: the primary source URL is required (prompt posts without a source: 'evergreen:<slug>')")
    src = post.get("sources") or []
    if (not src and not evergreen) or not all(s.get("name") and str(s.get("url", "")).startswith("http") for s in src):
        p.append("sources: at least one {name, url} (optional only for evergreen prompt posts)")
    slides = post.get("slides") or []
    if not 3 <= len(slides) <= 7:
        p.append(f"slides: {len(slides)}, need 3-7 (the closing slide is added automatically)")
    if slides and slides[0].get("type") != "cover":
        p.append("the first slide must be the cover")
    if [s.get("type") for s in slides].count("cover") != 1:
        p.append("exactly one cover slide")
    if [s.get("type") for s in slides].count("concreto") != 1 or (slides and slides[-1].get("type") != "concreto"):
        p.append("exactly one 'concreto' slide, as the last slide")

    def length(key, text):
        if not isinstance(text, str) or not text.strip():
            p.append(f"{key}: missing")
        elif len(text.replace("*", "")) > LIMITS[key]:
            p.append(f"{key}: {len(text)} characters, limit {LIMITS[key]}: '{text[:50]}…'")

    for i, s in enumerate(slides, 1):
        t = s.get("type")
        if t == "cover":
            length("cover.title", s.get("title"))
            if s.get("sub"):
                length("cover.sub", s["sub"])
            if s.get("image_prompt"):
                length("cover.image_prompt", s["image_prompt"])
            if s.get("image_credit"):
                length("cover.image_credit", s["image_credit"])
        elif t == "point":
            length("point.title", s.get("title")); length("point.body", s.get("body"))
        elif t == "list":
            length("list.title", s.get("title"))
            items = s.get("items") or []
            if not 2 <= len(items) <= 5:
                p.append(f"slide {i}: list needs 2-5 items")
            for it in items:
                length("list.item", it)
        elif t == "prompt":
            length("prompt.title", s.get("title")); length("prompt.prompt", s.get("prompt"))
            if s.get("note"):
                length("prompt.note", s["note"])
        elif t == "concreto":
            items = s.get("items") or []
            if not 1 <= len(items) <= 3:
                p.append(f"slide {i}: 'concreto' needs 1-3 items")
            for it in items:
                length("concreto.item", it)
        else:
            p.append(f"slide {i}: unknown type '{t}'")
        for v in [s.get(k) for k in ("title", "sub", "body", "prompt", "note")] + list(s.get("items") or []):
            if isinstance(v, str) and v.count("*") % 2:
                p.append(f"slide {i}: unbalanced * in '{v[:40]}'")
            if isinstance(v, str) and EMOJI.search(v):
                p.append(f"slide {i}: no emoji on slides (they can't be drawn): '{v[:40]}'")
    length("caption", post.get("caption"))
    tags = post.get("hashtags") or []
    if not 3 <= len(tags) <= 10 or not all(re.fullmatch(r"#[\wàèéìòù]+", t) for t in tags):
        p.append("hashtags: 3-10, each like #intelligenzaartificiale")
    text = " ".join([post.get("caption", "")] + [str(v) for s in slides for v in s.values()]).lower()
    for w in BANNED:
        if w in text:
            p.append(f"hype word '{w}' (see BRAND.md)")
    return p


def full_caption(post):
    """The caption as published: text, sources, the AI note, hashtags."""
    names = ", ".join(dict.fromkeys(s["name"] for s in post.get("sources") or []))
    source = f"Fonte: {names}\n" if names else ""
    return f"{post['caption'].strip()}\n\n{source}{AI_NOTE}\n\n{' '.join(post['hashtags'])}"


def cover_title(post):
    return post["slides"][0]["title"].replace("*", "")
