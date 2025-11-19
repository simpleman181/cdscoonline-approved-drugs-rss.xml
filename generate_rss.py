#!/usr/bin/env python3
# generate_rss.py
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from email.utils import format_datetime
from datetime import datetime, timezone
import hashlib
import os

BASE_URL = "https://cdsco.gov.in"
TARGET = "https://cdsco.gov.in/opencms/opencms/en/Committees/SEC/"
OUTPUT = "sec-rss.xml"
CHANNEL_TITLE = "CDSCO - SEC (auto)"
CHANNEL_LINK = TARGET
CHANNEL_DESC = "Automated RSS for CDSCO SEC page (generated)."

def fetch_page(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text

def parse_items(html):
    soup = BeautifulSoup(html, "lxml")
    items = []

    # Strategy: find links to committee PDFs / pages. The site lists items in tables / lists.
    # We'll extract <a> tags under the main content area that link to PDFs or to details.
    main = soup.find(id="content") or soup
    anchors = main.find_all("a", href=True)

    seen = set()
    for a in anchors:
        href = a["href"].strip()
        if href.startswith("javascript:") or href.startswith("#"):
            continue
        # turn relative urls into absolute
        if href.startswith("/"):
            link = BASE_URL + href
        elif href.startswith("http"):
            link = href
        else:
            link = BASE_URL + "/" + href

        text = a.get_text(strip=True) or link
        # Filter probable article/pdf links (you can expand these rules)
        if any(x in link.lower() for x in ["/resources/","uploadcommitteefiles","recommendations","uploadcdscoweb","pdf",".pdf","CommitteeFiles","NewsDetails","Minutes"]) or text.lower().startswith("minutes") or len(text) > 6:
            uid = hashlib.sha1(link.encode()).hexdigest()
            if uid in seen:
                continue
            seen.add(uid)
            item = {
                "title": text,
                "link": link,
                "guid": link,
                "pubDate": None,
                "description": ""
            }
            # try to get nearby date text (simple heuristic)
            parent_text = a.parent.get_text(" ", strip=True)
            # try parse any date-like substring
            for token in parent_text.split():
                try:
                    dt = dateparser.parse(token, fuzzy=False)
                    item["pubDate"] = dt
                    break
                except Exception:
                    continue
            items.append(item)
    return items

def build_rss(items):
    now = datetime.now(timezone.utc)
    header = f'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>{CHANNEL_TITLE}</title>
    <link>{CHANNEL_LINK}</link>
    <description>{CHANNEL_DESC}</description>
    <lastBuildDate>{format_datetime(now)}</lastBuildDate>
    <language>en-IN</language>
'''
    body = ""
    for it in items:
        pub = it["pubDate"]
        if not pub:
            pub = now
        elif not pub.tzinfo:
            pub = pub.replace(tzinfo=timezone.utc)
        pubstr = format_datetime(pub)
        title = escape_xml(it["title"])
        link = it["link"]
        guid = it["guid"]
        desc = escape_xml(it["description"])
        body += f"""    <item>
      <title>{title}</title>
      <link>{link}</link>
      <description>{desc}</description>
      <pubDate>{pubstr}</pubDate>
      <guid isPermaLink="true">{guid}</guid>
    </item>\n"""
    footer = "  </channel>\n</rss>\n"
    return header + body + footer

def escape_xml(s):
    s = str(s)
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;"))

def main():
    html = fetch_page(TARGET)
    items = parse_items(html)

    # de-duplicate by link and keep order
    seen = set()
    dedup = []
    for it in items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        dedup.append(it)
    rss = build_rss(dedup)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"Wrote {OUTPUT} with {len(dedup)} items.")

if __name__ == "__main__":
    main()
