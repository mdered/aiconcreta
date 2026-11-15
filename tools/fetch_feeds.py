#!/usr/bin/env python3
"""Lists recent AI news from sources.json that hasn't been covered yet (newest first), for the drafting agent.

    python3 tools/fetch_feeds.py              # last 36 hours
    python3 tools/fetch_feeds.py --hours 72

Covered = the URL is a story_key or source of any post in drafts/. Standard library only; a feed that fails is
reported and skipped.
"""
import concurrent.futures, datetime, email.utils, glob, gzip, html, json, os, re, sys, urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (compatible; FeedReader/1.0)"


def text(el, *names):
    for n in names:
        for child in el:
            if child.tag.split("}")[-1] == n:
                if n == "link" and child.get("href"):
                    if child.get("rel", "alternate") == "alternate":
                        return child.get("href")
                    continue
                if child.text and child.text.strip():
                    return child.text.strip()
    return ""


def when(s):
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def clean(s, n=280):
    s = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def norm(url):
    return re.sub(r"[?#].*$", "", url or "").rstrip("/").lower()


def fetch(feed):
    req = urllib.request.Request(feed["url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b":                                  # some servers gzip even when not asked
        data = gzip.decompress(data)
    root = ET.fromstring(data.lstrip(b"\xef\xbb\xbf \r\n\t"))
    items = []
    for el in root.iter():
        if el.tag.split("}")[-1] not in ("item", "entry"):
            continue
        title = clean(text(el, "title"), 200)
        summary = clean(text(el, "description", "summary", "content", "encoded"))
        f = feed.get("filter")
        if f and not any(re.search(rf"(?<![\w]){re.escape(w)}(?![\w])", f"{title} {summary}") for w in f):
            continue
        items.append({"source": feed["name"], "type": feed["type"], "title": title, "url": text(el, "link"),
                      "date": when(text(el, "pubDate", "published", "updated", "date")), "summary": summary})
    return items


def covered():
    seen = set()
    for p in glob.glob(os.path.join(ROOT, "drafts", "*", "post.json")):
        try:
            post = json.load(open(p, encoding="utf-8"))
        except ValueError:
            continue
        seen.add(norm(post.get("story_key")))
        seen.update(norm(s.get("url")) for s in post.get("sources", []))
    return seen


def main():
    hours = int(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 36
    cfg = json.load(open(os.path.join(ROOT, "sources.json"), encoding="utf-8"))
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    seen, items, errors = covered(), [], []
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        for feed, fut in [(f, ex.submit(fetch, f)) for f in cfg["feeds"]]:
            try:
                items += fut.result()
            except Exception as e:
                errors.append(f"{feed['name']}: {e}")
    fresh = [i for i in items if i["date"] and i["date"] >= since and norm(i["url"]) not in seen]
    fresh.sort(key=lambda i: i["date"], reverse=True)
    print(f"# {len(fresh)} uncovered items from the last {hours} h ({len(cfg['feeds']) - len(errors)}/{len(cfg['feeds'])} feeds read)\n")
    for i in fresh:
        print(f"- [{i['type']}] {i['source']} · {i['date']:%Y-%m-%d %H:%M} UTC · {i['title']}\n  {i['url']}")
        if i["summary"]:
            print(f"  {i['summary']}")
    if errors:
        print("\n# Feeds that failed (check these by hand if they matter today)\n" + "\n".join(f"- {e}" for e in errors))
    print("\n# No feed, check by hand\n" + "\n".join(f"- {u}" for u in cfg.get("check_by_hand", [])))


if __name__ == "__main__":
    main()
