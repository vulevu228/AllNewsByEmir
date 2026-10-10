// Cloudflare Worker (free plan) with a cron trigger every 15 minutes: starts the news workflow through
// GitHub's API. GitHub runs manually started workflows right away, while its own schedule often starts late
// or skips runs. Secret GITHUB_TOKEN: fine-grained token, only this repository, "Actions: Read and write".
const URL = "https://api.github.com/repos/vulevu228/AllNewsByEmir/actions/workflows/news.yml/dispatches";

export default {
  async scheduled(event, env) {
    const r = await fetch(URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "allnews-trigger",
      },
      body: JSON.stringify({ ref: "main" }),
    });
    if (r.status !== 204) throw new Error(`dispatch failed: ${r.status} ${await r.text()}`);
  },
};
