// AI Essenziale trigger (Cloudflare Worker, cron "* * * * *").
// GitHub's own timer is unreliable, so this starts the pipeline workflow:
//   - within a minute of a Telegram tap or message (getWebhookInfo only counts pending updates; it never reads or
//     confirms them, so no tap can be lost here: the pipeline still reads them with getUpdates);
//   - every 10 minutes anyway (publishing at 12:30 / 18:30, new drafts, expiry).
// It never starts a second run while one is queued or running.
// Secrets: TELEGRAM_TOKEN, GITHUB_TOKEN (fine-grained, this repo only, Actions: read and write).

const REPO = "mdered/aiconcreta";
const WORKFLOW = "pipeline.yml";
const GH = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}`;

async function github(env, path, init = {}) {
  return fetch(GH + path, {
    ...init,
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "aiessenziale-trigger",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
}

async function pendingTaps(env) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/getWebhookInfo`);
  if (!r.ok) throw new Error(`Telegram ${r.status}`);
  return (await r.json()).result.pending_update_count || 0;
}

async function busy(env) {
  for (const status of ["queued", "in_progress"]) {
    const r = await github(env, `/runs?status=${status}&per_page=1`);
    if (!r.ok) throw new Error(`GitHub runs ${r.status}`);
    if ((await r.json()).total_count > 0) return true;
  }
  return false;
}

async function tick(env, minute) {
  const regular = minute % 10 === 3;
  const pending = await pendingTaps(env);
  if (!regular && pending === 0) return "idle";
  if (await busy(env)) return `busy (pending ${pending})`;
  const r = await github(env, "/dispatches", { method: "POST", body: JSON.stringify({ ref: "main" }) });
  if (r.status !== 204) throw new Error(`dispatch ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return `started (${regular ? "every 10 min" : "tap"}, pending ${pending})`;
}

export default {
  async scheduled(event, env, ctx) {
    const minute = new Date(event.scheduledTime).getUTCMinutes();
    console.log(await tick(env, minute));
  },
  async fetch() {
    return new Response("AI Essenziale trigger: nothing to see here.\n", { headers: { "Content-Type": "text/plain" } });
  },
};
