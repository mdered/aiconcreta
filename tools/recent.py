#!/usr/bin/env python3
"""What AI Essenziale covered recently, for the drafting agent: the last 30 days of drafts (with their status) and the
content mix of the last 7 days."""
import collections, datetime, glob, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
state = json.load(open(os.path.join(ROOT, "state", "posts.json"))) if os.path.exists(os.path.join(ROOT, "state", "posts.json")) else {}
now = datetime.datetime.now(datetime.timezone.utc)
rows = []
for p in glob.glob(os.path.join(ROOT, "drafts", "*", "post.json")):
    try:
        post = json.load(open(p, encoding="utf-8"))
        created = datetime.datetime.fromisoformat(post["created"])
    except (ValueError, KeyError):
        continue
    if now - created <= datetime.timedelta(days=30):
        rows.append((created, post, state.get(post["id"], {}).get("status", "new")))
rows.sort(key=lambda r: r[0], reverse=True)
print("# Last 30 days (newest first): date · kind · status · cover title · story_key")
for created, post, status in rows:
    print(f"- {created:%Y-%m-%d} · {post['kind']} · {status} · {post['slides'][0]['title'].replace('*', '')} · {post.get('story_key')}")
if not rows:
    print("- nothing yet")
week = collections.Counter(post["kind"] for c, post, s in rows
                           if now - c <= datetime.timedelta(days=7) and s not in ("rejected", "expired"))
target = {"news": 50, "tool": 15, "prompt": 15, "italia": 20}
total = sum(week.values()) or 1
print("\n# Mix of the last 7 days (approved or pending) vs target")
for k, t in target.items():
    print(f"- {k}: {week[k]} ({100 * week[k] // total}%), target ~{t}%")
