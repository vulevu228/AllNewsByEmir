"""
All News by Emir - shared logic, run every 15 minutes by GitHub Actions (run.py).

Pull AI + world news RSS feeds (world feeds live in world.py), merge them into news.json for the
page, email an alert for new "concerning" stories from the AI feeds (a security word AND an AI word
in the same story; with an ANTHROPIC_API_KEY, Claude Haiku double-checks them - ai.py) and write the
daily briefings.

Data folder (DATA_DIR, default ./data):
  $web/index.html   the reading page (copied from site/ every run)
  $web/news.json    items shown on the page (AI feeds 60 days, world feeds 3)
  state/news_state.json   private: what was already emailed, briefings, Claude usage
"""

import gzip
import hashlib
import html
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

from . import ai, world

UA = "Mozilla/5.0 (AINewsWatch RSS reader; personal use)"
KEEP_DAYS = 60        # AI feeds
WORLD_KEEP_DAYS = 3   # world feeds: ~1500 stories a day, so keep the page file small
MAX_ITEMS = 9000
ALERT_MAX_AGE_H = 48  # never alert on old stories that a feed happens to re-list
SITE_DIR = Path(__file__).resolve().parent.parent / "site"
WORLD_EVENTS_MAP = "https://worldeventslive.de/map.json"

# category: ai = news outlets, lab = the labs' own blogs, community = HN/blogs,
# security = security outlets (only AI-related stories are kept from these)
FEEDS = [
    ("TechCrunch", "ai", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge", "ai", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("Ars Technica", "ai", "https://arstechnica.com/ai/feed/"),
    ("MIT Technology Review", "ai", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("Wired", "ai", "https://www.wired.com/feed/tag/ai/latest/rss"),
    ("The Register", "ai", "https://www.theregister.com/software/ai_ml/headlines.atom"),
    ("OpenAI", "lab", "https://openai.com/news/rss.xml"),
    ("Google DeepMind", "lab", "https://deepmind.google/blog/rss.xml"),
    ("Google AI", "lab", "https://blog.google/technology/ai/rss/"),
    ("Hugging Face", "lab", "https://huggingface.co/blog/feed.xml"),
    ("Simon Willison", "community", "https://simonwillison.net/atom/everything/"),
    # official HN search API (hnrss.org's search endpoint kept returning 502)
    ("Hacker News", "community", "https://hn.algolia.com/api/v1/search_by_date?query=AI%20LLM"
     "&optionalWords=AI%20LLM&tags=story&numericFilters=points%3E150&hitsPerPage=50"),
    ("BleepingComputer", "security", "https://www.bleepingcomputer.com/feed/"),
    ("The Hacker News", "security", "https://feeds.feedburner.com/TheHackersNews"),
    ("SecurityWeek", "security", "https://www.securityweek.com/category/artificial-intelligence/feed/"),
    ("The Register Security", "security", "https://www.theregister.com/security/headlines.atom"),
]
AI_CATS = {"ai", "lab", "community", "security"}
ALL_FEEDS = [(n, c, u, ["ai"], None) for n, c, u in FEEDS] + [
    (n, "world", u, tags, region) for n, tags, u, region in world.WORLD_FEEDS]

# "AI" alone is matched case-sensitively so words like "said" or "Thai" never count.
AI_RE = re.compile(
    r"\bAI\b|\bA\.I\.|(?i:\b(?:artificial intelligence|LLMs?|GPT-?\w*|ChatGPT|OpenAI|Anthropic|Claude|"
    r"Gemini|DeepMind|Hugging ?Face|Mistral|Llama|DeepSeek|Copilot|PyTorch|TensorFlow|Ollama|"
    r"LangChain|MCP|model context protocol|machine learning|chatbots?|AI agents?|agentic|"
    r"xAI|Grok|Perplexity|Midjourney|Stable Diffusion|transformers|safetensors|model weights|Codex|Cursor)\b)"
)
# weight 2: something bad happened; weight 1: risk / weakness language
STRONG = [
    r"breach(?:es|ed)?", r"hacked", r"compromised?", r"malware", r"backdoor(?:s|ed)?",
    r"supply[- ]chain", r"ransomware", r"zero[- ]days?", r"0-days?", r"leak(?:s|ed)?",
    r"stolen", r"exfiltrat\w*", r"poison(?:ed|ing)", r"hijack\w*", r"trojan\w*",
    r"credential theft", r"account takeover", r"rogue (?:AI|agents?|model)", r"wiper",
    r"actively exploited", r"under attack",
]
WEAK = [
    r"vulnerab\w*", r"CVE-\d{4}-\d+", r"exploit\w*", r"flaws?", r"jailbreak\w*",
    r"prompt injection", r"attack(?:s|ers?)?", r"hackers?", r"security incident", r"exposed",
    r"malicious", r"phishing", r"RCE", r"remote code execution", r"outage", r"deepfakes?",
    r"scam\w*", r"threat actors?", r"sandbox escape", r"data exposure",
]
STRONG_RE = [(re.compile(rf"(?i)\b{p}\b"), 2) for p in STRONG]
WEAK_RE = [(re.compile(rf"(?i)\b{p}\b"), 1) for p in WEAK]
# concerning = at least one "something happened" word, or three different risk words
ALERT_SCORE = 3


# ---------------------------------------------------------------- storage

class LocalStore:
    """Two folders: $web (the published page files) and state (private, kept between runs in the
    GitHub Actions cache, never published)."""

    def __init__(self, root):
        self.root = Path(root)

    def get(self, container, name):
        p = self.root / container / name
        return p.read_bytes() if p.exists() else None

    def put(self, container, name, data, content_type=None, cache=None, gz=False):
        p = self.root / container / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def store_from_env():
    return LocalStore(os.environ.get("DATA_DIR", "data"))


def load_json(store, container, name, default):
    raw = store.get(container, name)
    if raw and raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw) if raw else default


def save_json(store, container, name, obj, gz=False):
    store.put(container, name, json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
              "application/json; charset=utf-8", gz=gz)


# ---------------------------------------------------------------- email

def send_email(subject, text_body, html_body=None):
    """Azure Communication Services Email (pay per email, no running cost). Returns False if not configured."""
    conn, sender = os.environ.get("ACS_CONNECTION_STRING"), os.environ.get("ACS_SENDER")
    to = os.environ.get("ALERT_TO")
    if not (conn and sender and to):
        logging.warning("Email not configured - skipping: %s", subject)
        return False
    from azure.communication.email import EmailClient
    content = {"subject": subject, "plainText": text_body}
    if html_body:
        content["html"] = html_body
    poller = EmailClient.from_connection_string(conn).begin_send({
        "senderAddress": sender,
        "recipients": {"to": [{"address": addr.strip()} for addr in to.split(",")]},
        "content": content,
    })
    result = poller.result()
    if result.get("status") != "Succeeded":
        raise RuntimeError(f"email not sent: {result}")
    return True


# ---------------------------------------------------------------- news

TAG_RE = re.compile(r"<[^>]+>")


def clean(text, limit=None):
    text = html.unescape(TAG_RE.sub(" ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "..."
    return text


def entry_time(e):
    for key in ("published_parsed", "updated_parsed"):
        t = e.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def score(text):
    """Returns (score, matched words). Only AI-related text can score."""
    if not AI_RE.search(text):
        return 0, []
    total, hits, strong = 0, [], False
    for rx, w in STRONG_RE + WEAK_RE:
        m = rx.search(text)
        if m:
            total += w
            strong |= w == 2
            hits.append(m.group(0).lower())
    if strong:
        total = max(total, ALERT_SCORE)
    return total, hits


def hn_entries(data):
    """HN Algolia search hits -> feedparser-style entries."""
    return [{
        "link": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
        "title": h.get("title"),
        "published_parsed": time.gmtime(h["created_at_i"]),
        "summary": f"{h.get('points', 0)} points, {h.get('num_comments') or 0} comments on Hacker News",
    } for h in data.get("hits", [])]


def fetch_feed(feed):
    name, cat, url, feed_tags, feed_region = feed
    is_ai = cat in AI_CATS
    keep_days = KEEP_DAYS if is_ai else WORLD_KEEP_DAYS
    r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
    r.raise_for_status()
    entries = hn_entries(r.json()) if "hn.algolia.com" in url else feedparser.parse(r.content).entries
    now = datetime.now(timezone.utc)
    items = []
    for e in entries[:60]:  # some lab feeds list their whole history
        if not world.keep_entry(name, e):
            continue
        link = e.get("link")
        title = clean(e.get("title"))
        if not link or not title:
            continue
        ts = entry_time(e) or now
        if ts > now + timedelta(hours=1):
            ts = now
        if ts < now - timedelta(days=keep_days):
            continue
        summary = clean(e.get("summary") or e.get("description"), 320 if is_ai else 240)
        text = f"{title}. {summary}"
        if cat == "security" and not AI_RE.search(text):
            continue  # security outlets: keep only AI-related stories
        # alerts stay about AI: only the AI feeds can be "concerning"
        sc, hits = score(text) if is_ai else (0, [])
        tags = set(feed_tags) | world.keyword_tags(text)
        if AI_RE.search(title):
            tags.add("ai")
        # topics / region we are not sure about are left off (the story still shows under All / Everywhere)
        conf = {t: world.topic_confidence(t, title, summary, feed_tags) for t in tags}
        tags = {t for t in tags if conf[t] >= world.CONFIDENCE}
        region = feed_region or world.detect_region(title, summary)
        region_conf = world.region_confidence(region, title, summary, feed_region)
        if region_conf < world.CONFIDENCE:
            region = None
        items.append({
            "id": hashlib.sha1(link.encode()).hexdigest()[:16],
            "title": title,
            "link": link,
            "source": name,
            "category": cat,
            "published": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "summary": summary,
            "score": sc,
            "hits": hits,
            "concerning": sc >= ALERT_SCORE,
            "tags": sorted(tags),
            "region": region,
            "conf": {"topics": {t: conf[t] for t in sorted(tags)}, "region": region_conf if region else None},
        })
    return items


def hotspots():
    """Top conflict hotspots (now vs the day before) from the World Events Live map, for the war briefing."""
    r = requests.get(WORLD_EVENTS_MAP, timeout=30, headers={"User-Agent": UA})
    r.raise_for_status()
    return [{"name": h["name"], "now": h["now"], "prev": h["prev"]}
            for h in r.json().get("hotspots", []) if h["now"] > 0][:4]


def norm_title(t):
    return re.sub(r"[^a-z0-9 ]", "", t.lower())[:80]


def sync_site_files(store):
    """Upload index.html when the deployed copy differs from site/."""
    page = (SITE_DIR / "index.html").read_bytes()
    current = store.get("$web", "index.html")
    if current != page:
        store.put("$web", "index.html", page, "text/html; charset=utf-8", cache="max-age=300")
        logging.info("index.html updated")


def run_news(store, send=True):
    started = time.time()
    sync_site_files(store)
    doc = load_json(store, "$web", "news.json", {"items": []})
    state = load_json(store, "state", "news_state.json", {})
    first_run = "alerted" not in state
    alerted = set(state.get("alerted", []))

    feed_status = {}
    fresh = []
    with ThreadPoolExecutor(max_workers=24) as pool:
        futures = {pool.submit(fetch_feed, f): f[0] for f in ALL_FEEDS}
        for fut, name in futures.items():
            try:
                got = fut.result()
                fresh.extend(got)
                feed_status[name] = {"ok": True, "n": len(got)}
            except Exception as exc:
                feed_status[name] = {"ok": False, "error": str(exc)[:160]}
                logging.warning("feed %s failed: %s", name, exc)

    # one link in an AI feed and a world feed (e.g. The Verge AI + The Verge all):
    # keep the AI copy (longer retention, alerts) and give it both sets of topics
    one = {}
    for it in fresh:
        prev = one.get(it["id"])
        if prev:
            keep, other = (prev, it) if prev["category"] in AI_CATS else (it, prev)
            keep["tags"] = sorted(set(keep["tags"]) | set(other["tags"]))
            keep["conf"]["topics"] = {t: max(keep["conf"]["topics"].get(t, 0), other["conf"]["topics"].get(t, 0)) for t in keep["tags"]}
            if not keep["region"]:
                keep["region"], keep["conf"]["region"] = other["region"], other["conf"]["region"]
            it = keep
        one[it["id"]] = it
    fresh = list(one.values())

    # merge: existing items keep their first-seen time, fresh items update title/summary
    by_id = {it["id"]: it for it in doc["items"]}
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_ids = []
    for it in fresh:
        old = by_id.get(it["id"])
        if old:
            it["seen"] = old.get("seen", now_iso)
            if old.get("ai_checked"):  # Claude's verdict replaces the keyword rule for good
                it.update(concerning=old["concerning"], ai_reason=old.get("ai_reason", ""), ai_checked=True)
        else:
            it["seen"] = now_iso
            new_ids.append(it["id"])
        by_id[it["id"]] = it

    def cutoff(days):
        return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ai_cut, world_cut = cutoff(KEEP_DAYS), cutoff(WORLD_KEEP_DAYS)
    items = []
    for it in by_id.values():
        it.setdefault("tags", ["ai"])  # stories saved before world news existed
        it.setdefault("region", None)
        if it["published"] >= (ai_cut if it["category"] in AI_CATS else world_cut):
            items.append(it)
    items.sort(key=lambda it: it["published"], reverse=True)

    # the same story syndicated by several outlets: keep the first copy only
    seen_titles, deduped = {}, []
    for it in items:
        key = norm_title(it["title"])
        first = seen_titles.get(key)
        if first:
            first["tags"] = sorted(set(first["tags"]) | set(it["tags"]))
            first["region"] = first["region"] or it["region"]
            continue
        seen_titles[key] = it
        deduped.append(it)
    items = deduped[:MAX_ITEMS]
    kept_ids = {it["id"] for it in items}
    recent = (datetime.now(timezone.utc) - timedelta(hours=ALERT_MAX_AGE_H)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Claude Haiku: judge the keyword candidates (briefings follow below)
    haiku = ai.Haiku(state)
    if haiku.enabled:
        first_ai = "ai_since" not in state
        haiku.check([it for it in items if it["category"] in AI_CATS and it["score"] >= 1
                     and not it.get("ai_checked") and it["published"] >= recent])
        if first_ai:  # stories upgraded on the very first check are old news: don't email them
            alerted.update(it["id"] for it in items if it.get("ai_checked") and it["concerning"])
            state["ai_since"] = now_iso

    try:
        hot = hotspots()
    except Exception as exc:  # the briefing must not depend on the map
        logging.warning("hotspots failed: %s", exc)
        hot = []

    # daily briefings, one per topic in ai.BRIEF_TOPICS, written after 05:00 UTC
    briefs = state.setdefault("briefings", {})
    if "briefing" in state:  # the first version kept only the AI briefing
        briefs.setdefault("ai", state.pop("briefing"))
    if haiku.enabled and datetime.now(timezone.utc).hour >= 5:
        for topic in ai.BRIEF_TOPICS:
            if briefs.get(topic, {}).get("date") == now_iso[:10]:
                continue
            day = [it for it in items if it["published"] >= cutoff(1)
                   and (it["category"] in AI_CATS if topic == "ai" else topic in it["tags"])]
            context = ""
            if topic == "war" and hot:
                context = "GDELT armed-event score, last 24 h vs the 24 h before: " + "; ".join(
                    f'{h["name"]} {h["now"]:.0f} vs {h["prev"]:.0f}' for h in hot)
            points = haiku.briefing(topic, day, context)
            if points:
                briefs[topic] = {"date": now_iso[:10], "at": now_iso, "points": points}
    usage = state.get("ai_usage", {}).get(now_iso[:7], {"usd": 0.0, "calls": 0})

    save_json(store, "$web", "news.json", {
        "updated": now_iso, "feeds": feed_status, "items": items,
        "briefings": state.get("briefings", {}),
        "ai": {"on": haiku.client is not None, "month_usd": usage["usd"], "calls": usage["calls"],
               "budget_usd": haiku.budget}}, gz=True)

    # alerts
    to_alert = [it for it in items
                if it["concerning"] and it["id"] not in alerted and it["published"] >= recent]
    emailed = False
    if first_run:
        emailed = send and send_email(
            "All News by Emir is live",
            welcome_text(items, to_alert), welcome_html(items, to_alert))
    elif to_alert:
        to_alert.sort(key=lambda it: (-it["score"], it["published"]))
        top = to_alert[0]["title"]
        subject = (f"[AI alert] {top[:90]}" if len(to_alert) == 1
                   else f"[AI alert] {len(to_alert)} new: {top[:70]}")
        emailed = send and send_email(subject, alert_text(to_alert), alert_html(to_alert))
    if emailed or first_run or not send:
        alerted.update(it["id"] for it in to_alert)
    # forget ids that fell off the page so state stays small
    state["alerted"] = sorted(a for a in alerted if a in kept_ids)
    state["last_news_run"] = now_iso
    save_json(store, "state", "news_state.json", state)

    return {"items": len(items), "new": len(new_ids), "alerts": len(to_alert),
            "emailed": emailed, "first_run": first_run,
            "failed_feeds": [k for k, v in feed_status.items() if not v["ok"]],
            "seconds": round(time.time() - started, 1)}


def page_url():
    return os.environ.get("PAGE_URL", "")


def alert_text(items):
    lines = [f"{len(items)} new concerning AI stor{'y' if len(items) == 1 else 'ies'}:", ""]
    for it in items[:15]:
        why = f"why: {it['ai_reason']}" if it.get("ai_reason") else f"matched: {', '.join(it['hits'])}"
        lines += [f"* {it['title']}", f"  {it['source']} | {why}",
                  f"  {it['link']}", ""]
    if page_url():
        lines.append(f"All news: {page_url()}")
    return "\n".join(lines)


def alert_html(items):
    rows = "".join(
        f'<p style="margin:0 0 16px"><a href="{html.escape(it["link"])}" style="font-size:16px;'
        f'color:#b42318;font-weight:600;text-decoration:none">{html.escape(it["title"])}</a><br>'
        f'<span style="color:#555;font-size:13px">{html.escape(it["source"])} &middot; '
        + (f'why: {html.escape(it["ai_reason"])}' if it.get("ai_reason")
           else f'matched: {html.escape(", ".join(it["hits"]))}') + '</span><br>'
        f'<span style="font-size:14px;color:#222">{html.escape(it["summary"])}</span></p>'
        for it in items[:15])
    foot = (f'<p><a href="{html.escape(page_url())}">Open All News by Emir</a></p>' if page_url() else "")
    return f'<div style="font-family:Arial,sans-serif;max-width:640px">{rows}{foot}</div>'


def welcome_text(items, concerning):
    return (f"All News by Emir is running. {len(items)} stories on the page, "
            f"{len(concerning)} concerning in the last {ALERT_MAX_AGE_H} h "
            f"(these were NOT emailed; from now on every new one is).\n\n"
            + (alert_text(concerning) if concerning else "") + f"\n{page_url()}")


def welcome_html(items, concerning):
    head = (f'<p style="font-family:Arial,sans-serif">All News by Emir is running. {len(items)} stories on '
            f'the page. From now on you get an email for every new concerning AI story. '
            f'Currently flagged (last {ALERT_MAX_AGE_H} h, for reference):</p>')
    return head + (alert_html(concerning) if concerning else f'<p><a href="{page_url()}">Open page</a></p>')
