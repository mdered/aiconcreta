# AI Concreta: brand and voice

**Promise:** le novità dell'intelligenza artificiale, in concreto. Every post answers "e io cosa ci faccio?"
**Audience:** Italian working adults, 25–50: employees, freelancers, small-business owners, students about to work.
Curious about AI and already trying ChatGPT, but not technical. They want to save time, not follow tech gossip.
**Bio:** L'intelligenza artificiale, fatta bene. 🇮🇹 / Novità, tool e prompt che puoi usare subito.

## Content mix (per week, about 14 posts)
| kind | share | what it is |
|---|---|---|
| `news` | ~50% | A real, recent announcement or event + what it changes for the reader |
| `tool` | ~15% | One real tool or feature, what it does, price, available in Italy/EU or not, how to try it |
| `prompt` | ~15% | One copy-paste prompt for a concrete work task, with why it works |
| `italia` | ~20% | AI in Italy: AI Act and Italian rules, Italian companies and public bodies, data about Italian workers |

## Voice
- **Tu**, never voi or lei. Direct, warm, calm. A smart colleague explaining something over coffee.
- **Short sentences.** One idea per sentence. Natural Italian, not translated English: "Ecco cosa cambia", not "Ecco cosa questo significa per te".
- **Plain words.** Explain any jargon the first time ("un modello, cioè il 'cervello' dietro il chatbot"). English terms only where Italians actually use them (prompt, chatbot, app, AI). Write "AI", not "IA", except in quotes and proper names.
- **Concrete over abstract.** Numbers, names, prices, dates, steps. "Gratis fino a 50 richieste al giorno" beats "accessibile".
- **No hype, no doom.** Banned: rivoluzionario, incredibile, pazzesco, game changer, sconvolgente, "cambierà tutto", "non crederai". No "l'AI ti ruberà il lavoro" framing; when jobs come up, say what changes and what to learn.
- **Honest about limits.** If a feature is US-only, paid, in beta or makes mistakes, say so. That's the brand.

## Accuracy rules (non-negotiable)
1. Every fact must be in a source you opened today. Prefer the primary source (the company's own post) over press.
2. Numbers, dates, prices, model names and quotes are copied exactly, never estimated or "rounded up".
3. Availability: mention Italy/EU only when it's a real question (a new feature or product that may be US-only). Then say
   what the source says, or "disponibilità in Italia non ancora annunciata" if it says nothing. Never write that line about
   a product people in Italy already use (ChatGPT, Claude, Gemini, Copilot…) unless the source says the feature is limited.
4. No rumors, leaks, "secondo indiscrezioni", stock tips, medical, legal or financial advice.
5. People: don't make posts about a private person; for public figures stick to what they did or said on record, no gossip.
6. If you're not sure about something, leave it out. A shorter true post beats a complete wrong one. If what's left is too
   thin to be useful, drop the story; never fill the gap by telling the reader what you couldn't find.
7. **Laws and rules (AI Act, Italian decrees, Garante, AgID):** only with the official text or the authority's own page
   (EUR-Lex, Gazzetta Ufficiale, the authority's site) plus one reliable outlet, and after a search for later changes
   (postponements, amendments, guidelines). Include the exceptions that matter. If any of this fails, skip the topic.
8. **The page speaks as a newsroom, never as the drafting process.** No "ho letto", "non ho trovato", "secondo la mia
   ricerca" on slides or in captions. Those notes belong in your run summary.

## Post anatomy
- **Cover:** a kicker (automatic: NOVITÀ / TOOL / PROMPT / ITALIA), a title of max ~60 characters with 1–3 *accent words*, optional sub-line.
  The title states the concrete change or benefit. Good: "Gemini ora *riassume le tue mail* in Gmail". Bad: "Google ha fatto una cosa incredibile".
- **Middle slides (1–5):** `point` (title + 1–3 sentences), `list` (2–5 short items), `prompt` (the copyable prompt). Each slide teaches one thing.
- **In concreto (last):** 1–3 actions or takeaways the reader can apply ("Provalo su…", "Se usi X, controlla…", "Non serve fare nulla: …").
- **Closing slide:** added automatically (Segui @aiconcreta).

## Caption
1. First line: the hook, max ~90 characters (visible before "altro").
2. 2–4 short lines with the essential facts.
3. "In concreto: …" in one line.
4. A real question for the comments ("Lo useresti per…?"), not "Cosa ne pensate?".
Source, the AI note and hashtags are added automatically. Max 1,600 characters before those.

## Hashtags (5–8)
Always 2 broad: `#intelligenzaartificiale #ai`. Then 3–6 specific to the post (product: `#chatgpt #gemini #claude #copilot`;
topic: `#produttività #lavoro #aiact #prompt #tecnologia #smartworking #pmi`). Lowercase, no spam tags.

## Visual identity (render/style.css)
**Logo:** a concrete slab with "AI" cut in lime (`.slab` in style.css; profile picture: `python render/render.py profile`).
The name stays in the handle and bio, never inside the profile circle (unreadable at 44 px).
Carbon background with a concrete grain, one accent: acid lime `#c8ff2e`. Space Grotesk for titles, Inter for text,
JetBrains Mono for prompts. "In concreto" is the full-lime signature slide.

## Cover images
The cover has a picture on top (the inner slides stay typographic, they're for reading). Two kinds:
1. **AI-generated (default):** write `image_prompt` on the cover slide: one or two English sentences describing a single,
   concrete visual metaphor for the story (an object, a scene). The house style (dark concrete, one lime light, empty bottom
   third) is added automatically. No people, faces, logos, brand names, text or screens; don't name products in the prompt.
   The slide shows "Immagine generata con AI".
   Good: "A matte black wallet on a concrete pedestal, a glowing fingerprint on its surface." Bad: "The ChatGPT logo on a phone".
2. **Official image:** for a company's own announcement, the header image of that announcement page (usually its `og:image`)
   may be saved as `drafts/<id>/cover.jpg`, with `"image_credit": "<Company>"` on the cover. Only images the company
   published itself; never photos from agencies or newspapers (Reuters, Getty, ANSA…), never pictures of people.
   When in doubt, use an AI image.
