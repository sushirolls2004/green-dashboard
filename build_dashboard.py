#!/usr/bin/env python3
"""Builds docs/index.html: a weekly green-news dashboard from RSS feeds.
Standard library only. Edit feeds.json to change topics and sources."""
import json, sys, html, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (green-weekly-dashboard; +https://github.com)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_feed(xml_bytes, default_source=""):
    items = []
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        date = None
        raw = it.findtext("pubDate")
        if raw:
            try:
                date = parsedate_to_datetime(raw)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
        src = it.find("source")
        source = (src.text if src is not None and src.text else default_source).strip()
        # Google News appends " - Source" to titles; strip it since we show source separately
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        if title and link and date:
            items.append({"title": title, "link": link, "date": date, "source": source})
    return items


def google_news_url(query, days, lang):
    q = f"{query} when:{days}d"
    params = urllib.parse.urlencode({"q": q, **lang})
    return "https://news.google.com/rss/search?" + params


def collect(cfg, fetcher=fetch):
    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg["days"])
    seen, topics = set(), []
    for t in cfg["topics"]:
        try:
            items = parse_feed(fetcher(google_news_url(t["query"], cfg["days"], cfg["language"])))
        except Exception as e:  # keep going if one feed fails
            print(f"[warn] topic '{t['name']}' failed: {e}", file=sys.stderr)
            items = []
        items = [i for i in items if i["date"] >= cutoff]
        items.sort(key=lambda i: i["date"], reverse=True)
        picked = []
        for i in items:
            key = i["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            picked.append(i)
            if len(picked) >= cfg["max_per_topic"]:
                break
        topics.append({"name": t["name"], "items": picked})
    trusted = []
    for f in cfg.get("trusted_feeds", []):
        try:
            trusted += [i for i in parse_feed(fetcher(f["url"]), f["name"]) if i["date"] >= cutoff]
        except Exception as e:
            print(f"[warn] feed '{f['name']}' failed: {e}", file=sys.stderr)
    trusted.sort(key=lambda i: i["date"], reverse=True)
    return topics, trusted[:15]


def card(i, tag):
    e = html.escape
    return (f'<article class="card" data-t="{e(tag)}"><span class="tag">{e(tag)}</span>'
            f'<h3><a href="{e(i["link"])}" target="_blank" rel="noopener">{e(i["title"])}</a></h3>'
            f'<p>{e(i["source"])} · {i["date"].strftime("%d %b %Y")}</p></article>')


PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#f6f8f5;--card:#fff;--ink:#1c2a22;--mute:#5d6b62;--line:#dfe6e0;--acc:#1f7a4d;--chip:#e8f1ea}}
@media(prefers-color-scheme:dark){{:root{{--bg:#101712;--card:#18221b;--ink:#e6efe8;--mute:#9bab9f;--line:#27342b;--acc:#4cc58a;--chip:#1f2e24}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:20px 16px 48px}}h1{{margin:0;font-size:26px}}
.sub{{color:var(--mute);margin:4px 0 16px}}.chips{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}}
.chip{{border:1px solid var(--line);background:var(--chip);color:var(--ink);border-radius:999px;padding:6px 14px;font:inherit;font-size:13px;cursor:pointer}}
.chip.on{{background:var(--acc);color:#fff;border-color:var(--acc)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--acc);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:6px}}
.tag{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--acc)}}
.card h3{{margin:0;font-size:15.5px;line-height:1.35}}.card a{{color:var(--ink);text-decoration:none}}.card a:hover{{color:var(--acc);text-decoration:underline}}
.card p{{margin:0;color:var(--mute);font-size:13px}}.foot{{margin-top:28px;font-size:12.5px;color:var(--mute)}}
</style></head><body><div class="wrap">
<h1>🌿 {title}</h1><p class="sub">Last {days} days · updated {updated} · headlines gathered automatically from RSS</p>
<div class="chips" id="chips"></div><div class="grid" id="grid">{cards}</div>
<p class="foot">Headlines link to the original publishers. Topic sorting is keyword-based, so some items may be loosely related.</p></div>
<script>
var chips=document.getElementById('chips'),cards=[].slice.call(document.querySelectorAll('.card'));
var tags=['All'].concat(cards.map(function(c){{return c.dataset.t}}).filter(function(v,i,a){{return a.indexOf(v)===i}}));
tags.forEach(function(t,i){{var b=document.createElement('button');b.className='chip'+(i?'':' on');b.textContent=t;
b.onclick=function(){{[].forEach.call(chips.children,function(x){{x.classList.toggle('on',x===b)}});
cards.forEach(function(c){{c.style.display=(t==='All'||c.dataset.t===t)?'':'none'}})}};chips.appendChild(b)}});
</script></body></html>"""


def main():
    cfg = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
    topics, trusted = collect(cfg)
    cards = [card(i, t["name"]) for t in topics for i in t["items"]]
    cards += [card(i, "Trusted sources") for i in trusted]
    if not cards:
        sys.exit("No items collected; check your network or feeds.json")
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    page = PAGE.format(title=html.escape(cfg["title"]), days=cfg["days"],
                       updated=datetime.now(timezone.utc).strftime("%d %b %Y"), cards="\n".join(cards))
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"Wrote {len(cards)} items to docs/index.html")


if __name__ == "__main__":
    main()
