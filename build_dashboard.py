#!/usr/bin/env python3
"""Builds docs/index.html: a weekly green-news dashboard.
Sources: Google News RSS (restricted to credible sites), a few direct RSS feeds,
and the World Bank open API for indicators. Standard library only.
Edit feeds.json to change categories, queries, sources and highlights."""
import json, sys, html, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (green-weekly-dashboard; +https://github.com)"}
E = html.escape


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def domain(url):
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


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
        src_url = src.get("url", "") if src is not None else ""
        if source and title.endswith(" - " + source):  # Google News appends the source name
            title = title[: -len(source) - 3]
        if title and link and date:
            items.append({"title": title, "link": link, "date": date, "source": source,
                          "domain": domain(src_url) if src_url else ""})
    return items


def google_news_url(query, days, lang, sites=None):
    q = f"({query})"
    if sites:
        q += " (" + " OR ".join("site:" + s for s in sites) + ")"
    q += f" when:{days}d"
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, **lang})


def allowed(item, sites):
    if not sites or not item["domain"]:
        return True
    return any(item["domain"] == s or item["domain"].endswith("." + s) for s in sites)


def classify(title, keywords):
    t = " " + title.lower() + " "
    for cat, kws in keywords.items():
        if any(k in t for k in kws):
            return cat
    return None


def load_trusted(cfg, cutoff, fetcher):
    extra = {}
    for f in cfg.get("trusted_feeds", []):
        try:
            for i in parse_feed(fetcher(f["url"]), f["name"]):
                if i["date"] >= cutoff:
                    cat = classify(i["title"], cfg["category_keywords"])
                    if cat:
                        extra.setdefault(cat, []).append(i)
        except Exception as e:
            print(f"[warn] feed '{f['name']}' failed: {e}", file=sys.stderr)
    return extra


def collect_section(cfg, sec, seen, cutoff, fetcher, extra=None):
    sites = cfg["site_groups"].get(sec.get("sites"), [])
    out = []
    for t in sec["topics"]:
        items = list((extra or {}).get(t["name"], [])) if sec["key"] == "global" else []
        for q in t["queries"]:
            try:
                url = google_news_url(q["q"], cfg["days"], cfg["languages"][q.get("lang", "en")], sites)
                items += parse_feed(fetcher(url))
            except Exception as e:  # keep going if one query fails
                print(f"[warn] {sec['key']}/{t['name']} failed: {e}", file=sys.stderr)
        items = [i for i in items if i["date"] >= cutoff and allowed(i, sites)]
        items.sort(key=lambda i: i["date"], reverse=True)
        picked = []
        for i in items:
            key = i["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            picked.append(i)
            if len(picked) >= sec["max_per_topic"]:
                break
        out.append({"name": t["name"], "items": picked})
    return out


def fetch_indicators(cfg, fetcher):
    rows = []
    for ind in cfg.get("indicators", []):
        vals = []
        for code, name in cfg["indicator_countries"].items():
            try:
                url = f"https://api.worldbank.org/v2/country/{code}/indicator/{ind['id']}?format=json&mrnev=1"
                rec = json.loads(fetcher(url))[1][0]
                if rec.get("value") is not None:
                    vals.append((name, float(rec["value"]), rec["date"]))
            except Exception as e:
                print(f"[warn] World Bank {ind['id']}/{code} failed: {e}", file=sys.stderr)
        if vals:
            rows.append({"label": ind["label"], "unit": ind.get("unit", ""), "tag": ind["tag"], "vals": vals})
    return rows


# ---------- rendering ----------
def news_card(i, tag):
    return (f'<article class="card" data-t="{E(tag)}"><span class="tag">{E(tag)}</span>'
            f'<h3><a href="{E(i["link"])}" target="_blank" rel="noopener">{E(i["title"])}</a></h3>'
            f'<p>{E(i["source"])} · {i["date"].strftime("%d %b %Y")}</p></article>')


def indicator_card(r):
    lines = "".join(f'<div class="row"><span>{E(n)}</span><b>{v:,.1f}{E(r["unit"])}</b><em>{E(y)}</em></div>'
                    for n, v, y in r["vals"])
    return (f'<div class="stat"><span class="tag">{E(r["tag"])}</span><h3>{E(r["label"])}</h3>{lines}'
            f'<p>World Bank, latest available year (auto-updated)</p></div>')


def highlight_card(h):
    return (f'<div class="stat"><span class="tag">{E(h["tag"])}</span><h3>{E(h["label"])}</h3>'
            f'<div class="big">{E(h["value"])}</div>'
            f'<p>{E(h["as_of"])} · <a href="{E(h["url"])}" target="_blank" rel="noopener">{E(h["source"])}</a> (manual)</p></div>')


def section_html(sec, topics):
    cards = [news_card(i, t["name"]) for t in topics for i in t["items"]]
    body = "\n".join(cards) if cards else '<p class="empty">No items found this week.</p>'
    return (f'<section id="{E(sec["key"])}"><h2>{E(sec["title"])}</h2><p class="note">{E(sec.get("note",""))}</p>'
            f'<div class="grid">{body}</div></section>'), len(cards)


PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#f6f8f5;--card:#fff;--ink:#1c2a22;--mute:#5d6b62;--line:#dfe6e0;--acc:#1f7a4d;--chip:#e8f1ea}}
@media(prefers-color-scheme:dark){{:root{{--bg:#101712;--card:#18221b;--ink:#e6efe8;--mute:#9bab9f;--line:#27342b;--acc:#4cc58a;--chip:#1f2e24}}}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:20px 16px 48px}}h1{{margin:0;font-size:26px}}
.sub{{color:var(--mute);margin:4px 0 12px}}nav{{display:flex;flex-wrap:wrap;gap:14px;margin:0 0 14px}}nav a{{color:var(--acc);font-weight:600;text-decoration:none;font-size:14px}}
h2{{font-size:19px;margin:30px 0 2px}}.note{{color:var(--mute);font-size:13px;margin:0 0 12px}}
.chips{{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 4px}}
.chip{{border:1px solid var(--line);background:var(--chip);color:var(--ink);border-radius:999px;padding:6px 14px;font:inherit;font-size:13px;cursor:pointer}}
.chip.on{{background:var(--acc);color:#fff;border-color:var(--acc)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}}
.card,.stat{{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--acc);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:6px}}
.tag{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--acc)}}
h3{{margin:0;font-size:15.5px;line-height:1.35}}.card a{{color:var(--ink);text-decoration:none}}.card a:hover{{color:var(--acc);text-decoration:underline}}
p{{margin:0}}.card p,.stat p{{color:var(--mute);font-size:13px}}.stat a{{color:var(--acc)}}
.row{{display:flex;gap:8px;align-items:baseline}}.row span{{flex:1;color:var(--mute)}}.row b{{font-size:20px;color:var(--acc)}}.row em{{font-style:normal;font-size:12px;color:var(--mute)}}
.big{{font-size:22px;font-weight:700;color:var(--acc)}}.empty{{color:var(--mute)}}.foot{{margin-top:30px;font-size:12.5px;color:var(--mute)}}
</style></head><body><div class="wrap">
<h1>🌿 {title}</h1><p class="sub">Last {days} days · updated {updated}</p>
<nav><a href="#data">Key data</a>{navlinks}</nav>
<section id="data"><h2>Key data</h2><p class="note">Indicators update automatically from the World Bank; highlights marked (manual) only change when you edit feeds.json.</p>
<div class="grid">{stats}</div></section>
<h2 style="margin-top:34px">News by category</h2><div class="chips" id="chips"></div>
{sections}
<p class="foot">Headlines link to original publishers and are limited to a list of credible outlets and research institutions (see feeds.json). Category sorting is keyword-based, so a few items may be loosely related.</p></div>
<script>
var chips=document.getElementById('chips'),cards=[].slice.call(document.querySelectorAll('.card'));
var tags=['All'].concat(cards.map(function(c){{return c.dataset.t}}).filter(function(v,i,a){{return a.indexOf(v)===i}}));
tags.forEach(function(t,i){{var b=document.createElement('button');b.className='chip'+(i?'':' on');b.textContent=t;
b.onclick=function(){{[].forEach.call(chips.children,function(x){{x.classList.toggle('on',x===b)}});
cards.forEach(function(c){{c.style.display=(t==='All'||c.dataset.t===t)?'':'none'}})}};chips.appendChild(b)}});
</script></body></html>"""


def build(cfg, fetcher=fetch):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=cfg["days"])
    extra = load_trusted(cfg, cutoff, fetcher)
    seen, results = set(), {}
    for sec in cfg["sections"]:  # list order = de-duplication priority
        results[sec["key"]] = collect_section(cfg, sec, seen, cutoff, fetcher, extra)
    by_key = {s["key"]: s for s in cfg["sections"]}
    parts, total, nav = [], 0, []
    for key in cfg["display_order"]:
        h, n = section_html(by_key[key], results[key])
        parts.append(h)
        total += n
        nav.append(f'<a href="#{E(key)}">{E(by_key[key]["title"])}</a>')
    stats = [indicator_card(r) for r in fetch_indicators(cfg, fetcher)]
    stats += [highlight_card(h) for h in cfg.get("manual_highlights", {}).get("items", [])]
    page = PAGE.format(title=E(cfg["title"]), days=cfg["days"], updated=now.strftime("%d %b %Y"),
                       navlinks="".join(nav), stats="\n".join(stats), sections="\n".join(parts))
    return page, total


def main():
    cfg = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
    page, total = build(cfg)
    if total == 0:
        sys.exit("No news items collected; check your network or feeds.json")
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"Wrote {total} news items to docs/index.html")


if __name__ == "__main__":
    main()
