#!/usr/bin/env python3
# generate_rss.py
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from email.utils import format_datetime
from datetime import datetime, timezone
import hashlib
import os, sys

TARGET = "https://cdscoonline.gov.in/CDSCO/cdscoDrugs"
OUTPUT = "cdsco-drugs-rss.xml"
CHANNEL_TITLE = "CDSCO - cdscoDrugs (auto)"
CHANNEL_LINK = TARGET
CHANNEL_DESC = "Automated RSS for CDSCO cdscoDrugs page (generated)."

HEADERS = {
    "User-Agent": "rss-bot/1.0 (+https://github.com/)"
}

def fetch_page(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def find_links(html):
    soup = BeautifulSoup(html, "lxml")
    main = soup.find(id="content") or soup
    anchors = main.find_all("a", href=True)

    items = []
    seen = set()
    for a in anchors:
        href = a["href"].strip()
        if href.startswith("javascript:") or href.startswith("#"):
            continue
        # normalize link
        if href.startswith("/"):
            link = "https://cdscoonline.gov.in" + href
        elif href.lower().startswith("http"):
            link = href
        else:
            link = TARGET.rstrip("/") + "/" + href.lstrip("/")

        title = a.get_text(" ", strip=True) or link
        # basic filter: PDFs, downloads, or descriptive links
        if any(x in link.lower() for x in [".pdf", "/uploads/", "download", "viewfile", "uploads"]) or len(title) > 6:
            if link in seen:
                continue
            seen.add(link)
            item = {"title": title, "link": link, "guid": link, "description": ""}
            # try to find a nearby date text (parent/next sibling)
            parent_text = a.parent.get_text(" ", strip=True) if a.parent else ""
            # attempt to parse any date-like substring
            for token in parent_text.split():
                try:
                    dt = dateparser.parse(token, fuzzy=False)
                    item["pubDate"] = dt
                    break
                except Exception:
                    continue
            items.append(item)

    return items

def build_rss(items, raw_snapshot_hash):
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

    # if we found no link-like items, include a snapshot entry so readers see when page changed
    if not items:
        snapshot_title = f"Snapshot update — page changed ({now.strftime('%Y-%m-%d %H:%M:%S %Z')})"
        body += f"""    <item>
      <title>{escape_xml(snapshot_title)}</title>
      <link>{CHANNEL_LINK}</link>
      <description>Page snapshot changed; content hash: {raw_snapshot_hash}</description>
      <pubDate>{format_datetime(now)}</pubDate>
      <guid isPermaLink="false">{raw_snapshot_hash}</guid>
    </item>\n"""
    else:
        for it in items:
            pub = it.get("pubDate")
            if not pub:
                pub = now
            elif not pub.tzinfo:
                pub = pub.replace(tzinfo=timezone.utc)
            pubstr = format_datetime(pub)
            title = escape_xml(it["title"])
            link = it["link"]
            guid = it["guid"]
            desc = escape_xml(it.get("description",""))
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
    # compute snapshot hash (useful if page is JS-driven; hash will change when content changes)
    raw_hash = hashlib.sha1(html.encode("utf-8")).hexdigest()

    items = find_links(html)
    rss = build_rss(items, raw_hash)

    # Write output
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"Wrote {OUTPUT} with {len(items)} items. snapshot_hash={raw_hash}")

if __name__ == "__main__":
    main()
