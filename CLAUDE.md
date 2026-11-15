# AI Essenziale

Automated, human-approved Instagram (later TikTok) page in Italian about AI news, tools and prompts: @aiessenziale.

- `BRAND.md`: audience, voice, accuracy rules, content mix, post anatomy. Read it before writing any post.
- `DRAFTING.md`: the daily drafting run (the scheduled Claude Code agent follows it). When asked to "draft" or "write today's posts", follow it.
- `tools/postspec.py`: the post format and its checks; `tools/validate.py`, `tools/recent.py`, `tools/fetch_feeds.py`.
- `render/`: slides as HTML/CSS drawn by headless Chrome (`render/render.py`).
- `pipeline.py`: run by GitHub Actions every 10 minutes: render new drafts → send to Telegram → read approvals → publish due posts.
- `state/posts.json`: every draft's status (written only by the pipeline). `media/<id>/NN.jpg`: rendered slides, public via GitHub Pages
  (Instagram downloads images from a public URL).

Rules: posts are Italian; code, comments and docs are English. Never commit tokens. Never publish without approval.
