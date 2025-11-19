#!/usr/bin/env python3
# generate_rss.py
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from email.utils import format_datetime
from datetime import datetime, timezone
import hashlib
import os, sys
import time

TARGET = "https://cdscoonline.gov.in/CDSCO/cdscoDrugs"
OUTPUT = "cdsco-drugs-rss.xml"
CHANNEL_TITLE = "CDSCO - cdscoDrugs (auto)"
CHANNEL_LINK = TARGET
CHANNEL_DESC = "Automated RSS for CDSCO cdscoDrugs page (generated)."

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

def fetch_page(url, max_retries=5):
    """Fetch page with retry logic and exponential backoff"""
    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1}/{max_retries} to fetch {url}")
            r = requests.get(url, headers=HEADERS, timeout=60, verify=True)
            r.raise_for_status()
            print(f"Successfully fetched page (status: {r.status_code})")
            return r.text
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 5  # Exponential backoff: 5, 10, 20, 40, 80 seconds
                print(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print(f"Failed to connect after {max_retries} attempts")
                raise
        except requests.exceptions.Timeout as e:
            print(f"Timeout error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 3
                print(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                raise
        except requests.exceptions.RequestException as e:
            print(f"Request error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 3
                print(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                raise

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
    try:
        print(f"Starting RSS generation for {TARGET}")
        html = fetch_page(TARGET)
        
        # compute snapshot hash
        raw_hash = hashlib.sha1(html.encode("utf-8")).hexdigest()
        print(f"Page hash: {raw_hash}")
        
        items = find_links(html)
        print(f"Found {len(items)} items")
        
        rss = build_rss(items, raw_hash)
        
        # Write output
        with open(OUTPUT, "w", encoding="utf-8") as f:
            f.write(rss)
        
        print(f"✓ Successfully wrote {OUTPUT} with {len(items)} items")
        print(f"✓ Snapshot hash: {raw_hash}")
        
    except Exception as e:
        print(f"ERROR: Failed to generate RSS feed: {e}")
        print(f"Creating fallback RSS feed with error notice...")
        
        # Create a fallback RSS with error information
        now = datetime.now(timezone.utc)
        fallback_rss = f'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>{CHANNEL_TITLE}</title>
    <link>{CHANNEL_LINK}</link>
    <description>{CHANNEL_DESC}</description>
    <lastBuildDate>{format_datetime(now)}</lastBuildDate>
    <language>en-IN</language>
    <item>
      <title>RSS Feed Update Failed</title>
      <link>{CHANNEL_LINK}</link>
      <description>Unable to fetch updates from CDSCO website. Error: {escape_xml(str(e))}</description>
      <pubDate>{format_datetime(now)}</pubDate>
      <guid isPermaLink="false">error-{now.strftime("%Y%m%d%H%M%S")}</guid>
    </item>
  </channel>
</rss>
'''
        
        with open(OUTPUT, "w", encoding="utf-8") as f:
            f.write(fallback_rss)
        
        print(f"✓ Wrote fallback RSS feed to {OUTPUT}")
        # Don't exit with error code - we still created a valid RSS file
        sys.exit(0)

if __name__ == "__main__":
    main()
