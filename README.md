# All News by Emir

A personal world + AI news page with instant email alerts for AI security incidents. It runs entirely on
GitHub: a scheduled GitHub Actions workflow fetches ~130 RSS feeds every 15 minutes and publishes the page to
GitHub Pages. No server, no database.

**Live:** https://vulevu228.github.io/AllNewsByEmir/

- **World news**: ~115 feeds, kept for 3 days, under topic tabs (World, War & conflict, Economy, Industry,
  Health, Diseases, Nature, Fun, Science, Space, Tech, Disasters, Energy, Politics) and a region row
  (North America, South America, Europe, Africa, Middle East, Asia, Oceania). Topics come from the feed
  plus keywords, regions from the feed or the first country named, each with a confidence score (topics
  or regions below 0.70 are left off). The page tints itself in the selected topic's colour.
- **AI news**: 60 days from 16 feeds: news outlets (TechCrunch, The Verge, Ars Technica, MIT Technology
  Review, Wired, The Register), the labs' own blogs (OpenAI, Google DeepMind, Google AI, Hugging Face),
  community (Simon Willison, Hacker News 150+ points) and security outlets (AI stories only).
- **Alerts**: a story is *concerning* when it mentions AI **and** an incident word (breach, hacked,
  malware, supply chain, leak, 0-day, rogue agent...) or three different risk words. New concerning
  stories from the last 48 h are emailed, one email per run.
- **Claude Haiku (optional)**: with an `ANTHROPIC_API_KEY`, Haiku double-checks every story the keyword
  rule finds risky (verdict + a short "why") and writes five-point daily briefings for AI and War &
  conflict (the war one also gets the conflict hotspot numbers from
  [World Events Live](https://worldeventslive.de)). Capped at `AI_BUDGET_USD` a month (default 1.5).
- Search, source filter, read marks and "new since last visit" (kept in your browser only), dark mode,
  works on a phone.

```
.github/workflows/news.yml   every 15 min: run.py -> publish data/$web to GitHub Pages
run.py                       one update (also for local runs)
news/newswatch.py            AI feeds, scoring, merging, alerts, email
news/world.py                world feeds, topic keywords, country -> region
news/ai.py                   Claude Haiku checks + daily briefings
site/index.html              the page (one file, no build step)
```

## How state is kept without a database
Each run restores `data/` from the GitHub Actions cache, updates it and saves it again. `data/$web/`
(the page and `news.json`) is published to Pages; `data/state/` (what was already emailed, briefings,
Claude usage) never leaves the cache.

## Run it yourself
1. Fork, then **Settings → Pages → Source: GitHub Actions**.
2. Optional secrets (**Settings → Secrets and variables → Actions**): `ANTHROPIC_API_KEY` for Haiku;
   `ACS_CONNECTION_STRING`, `ACS_SENDER`, `ALERT_TO` for alert emails (Azure Communication Services
   Email, pay per email). Without them the page still works, just without checks and emails.
3. **Actions → news → Run workflow** once; after that it runs on its own.

Local run: `pip install -r requirements.txt`, then `python run.py --no-email` and
`python -m http.server -d "data/$web" 8000`.

GitHub's own schedule often starts late or skips runs, so a Cloudflare Worker cron (`cloudflare/trigger.js`,
free plan) starts the workflow every 15 minutes through the API; the workflow's hourly schedule is only a backup. The workflow also makes an
empty commit once a month, because GitHub pauses schedules in repositories without activity for 60 days.
