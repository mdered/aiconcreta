# AI Essenziale

Instagram page @aiessenziale: Italian AI news, tools and prompts, written by a scheduled Claude Code agent and **approved
by a human on Telegram** before anything is published.

```
06:30  Claude Code (scheduled cloud agent, DRAFTING.md) ── writes 3 drafts ──► drafts/<id>/post.json ──► git push
          │
GitHub Actions (pipeline.py), started by a Cloudflare Worker (worker/trigger.js): within a minute of a tap, and every 10 min
          ├─ render   drafts → media/<id>/NN.jpg (headless Chrome; AI cover image via Gemini)
          ├─ notify   album + caption + buttons on Telegram
          ├─ poll     ✅ Programma (next free slot: 12:30 / 18:30) · ⚡ Appena possibile · ❌ Scarta · ↩️ Annulla
          ├─ expire   unanswered after 36 h
          └─ publish  due posts → Instagram carousel (test mode until LIVE=true)
```

Your weekly work: tap the buttons, about 1 minute per draft.

## Files
| | |
|---|---|
| `BRAND.md` | audience, voice, accuracy rules, content mix, post anatomy |
| `DRAFTING.md` | what the drafting agent does each run |
| `sources.json` | RSS feeds (labs, international press, Italian outlets) |
| `tools/` | `fetch_feeds.py` (uncovered news), `recent.py` (what was covered), `validate.py`, `postspec.py` (format) |
| `render/` | slide template, styles, fonts (OFL), `render.py` |
| `pipeline.py` | render → Telegram → schedule → publish |
| `state/posts.json` | each draft's status; written only by the pipeline |
| `examples/` | a sample post |

## Try it locally
```sh
python3 -m venv .venv && .venv/bin/pip install pillow websocket-client
.venv/bin/python render/render.py examples/2026-11-16-prompt-riassunto-riunione/post.json /tmp/aiconcreta-test
.venv/bin/python render/render.py profile          # profile.png for Instagram and TikTok
python3 tools/fetch_feeds.py                        # today's uncovered news
```

## Setup (once)
1. **GitHub**: public repo `mdered/aiconcreta` (Instagram downloads the slides from a public URL), Settings → Pages →
   "Deploy from a branch", `main`, `/ (root)`.
2. **Telegram**: in Telegram, talk to @BotFather → `/newbot` → copy the token. Send any message to your new bot, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `message.chat.id`.
   Repo secrets: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`.
3. **Instagram**: @aiessenziale must be a professional (Creator or Business) account linked to a Facebook Page. Get a Page
   token the same way as for @fondamentali.gym (Meta app → Facebook Login → long-lived Page token) and its IG user id.
   Repo secrets: `IG_TOKEN`, `IG_USER_ID`.
4. **Cover images**: repo secret `GEMINI_API_KEY` (the same Google AI Studio key as for the Colosso photos, about €0.12 per
   cover). Without it the covers stay typographic.
5. **Drafting agent**: a Claude Code scheduled cloud agent on this repo, daily at 06:30 Europe/Rome, prompt:
   "Follow DRAFTING.md."
6. Watch a few days in **test mode** (Telegram tells you what it would have published). Then repo variable `LIVE` = `true`.
   Optional variable `SLOTS` (default `12:30,18:30`).

## Rules
- Nothing is published without a ✅ or ⚡ on Telegram. Only the configured chat can approve.
- A post is published once (`state/posts.json`), at most one per run, and never more than 12 hours late.
- Captions end with the source and "Contenuto preparato con l'aiuto dell'AI e verificato dalla redazione."
- Cover pictures are AI-generated in the house style, or the company's own announcement image with a credit; never agency
  photos, logos or other people's screenshots. Inner slides are typographic.

TikTok comes later: its Content Posting API only posts privately until the app passes TikTok's audit.

## Trigger (Cloudflare Worker)
GitHub's own timer is unreliable (hours late), so `worker/trigger.js` runs on Cloudflare's free plan every minute: it
checks Telegram's pending-update count (read-only, never consumes taps) and starts the workflow when a tap is waiting,
and every 10 minutes anyway; never while a run is queued or running. Worker `aiessenziale-trigger`, secrets
`TELEGRAM_TOKEN` and `GITHUB_TOKEN` (fine-grained, this repo only, Actions: read and write). To redeploy after editing,
upload the script with the Cloudflare API (token in `~/.config/cloudflare/aiessenziale-token`).
