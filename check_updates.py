# check_updates.py
# Laadt de watchlist uit een prive GitHub Gist en schrijft een RSS feed.
# Benodigde GitHub Actions secrets:
#   GH_GIST_TOKEN  — personal access token met gist scope
#   GIST_ID            — ID van de prive gist

import json
import os
import urllib.request
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

GIST_FILE      = "app_watchlist.json"
VERSIONS_FILE  = "app_versions.json"
FEED_FILE      = "feed.xml"
MAX_FEED_ITEMS = 50

# --- Hulpfuncties ------------------------------------------------------------

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_watchlist():
    token   = os.environ.get("GH_GIST_TOKEN", "")
    gist_id = os.environ.get("GIST_ID", "")
    print(f"  GH_GIST_TOKEN aanwezig: {bool(token)}")
    print(f"  GIST_ID aanwezig: {bool(gist_id)}")
    if not token or not gist_id:
        print("Fout: GH_GIST_TOKEN of GIST_ID niet ingesteld.")
        return {"apps": []}
    url = f"https://api.github.com/gists/{gist_id}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    # Pak het eerste bestand in de Gist, ongeacht de naam
    first_file = next(iter(data["files"].values()))
    content = first_file["content"]
    return json.loads(content)

def fetch_app_info(app_id):
    url = f"https://itunes.apple.com/lookup?id={app_id}&country=nl&lang=nl"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("resultCount", 0) > 0:
                return data["results"][0]
    except Exception as e:
        print(f"  Fout bij ophalen van app {app_id}: {e}")
    return None

def load_existing_feed_items(feed_path):
    items = []
    if not os.path.exists(feed_path):
        return items
    try:
        tree = ET.parse(feed_path)
        channel = tree.getroot().find("channel")
        if channel is not None:
            items = channel.findall("item")
    except Exception:
        pass
    return items

def build_feed(new_items, existing_items, feed_path):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "App Store Updates"
    ET.SubElement(channel, "link").text = "https://apps.apple.com"
    ET.SubElement(channel, "description").text = "Updates voor gevolgde App Store apps"
    ET.SubElement(channel, "language").text = "nl"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000")
    for item in (new_items + existing_items)[:MAX_FEED_ITEMS]:
        channel.append(item)
    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    with open(feed_path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="utf-8", xml_declaration=False)
    print(f"  Feed geschreven: {len(channel.findall('item'))} item(s).")

def make_rss_item(app, new_version, old_version, release_notes, store_url):
    item = ET.Element("item")
    ET.SubElement(item, "title").text = f"{app['name']} {new_version}"
    ET.SubElement(item, "link").text = store_url
    notes = release_notes.strip() if release_notes else "Geen release notes beschikbaar."
    ET.SubElement(item, "description").text = (
        f"<![CDATA[<p><strong>{app['name']}</strong> bijgewerkt naar "
        f"<strong>{new_version}</strong> (was {old_version}).</p>"
        f"<p>{notes}</p>"
        f"<p><a href='{store_url}'>Bekijk in App Store</a></p>]]>"
    )
    ET.SubElement(item, "pubDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000")
    ET.SubElement(item, "guid", isPermaLink="false").text = (
        f"{app['id']}-{new_version}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    )
    return item

# --- Hoofdlogica -------------------------------------------------------------

def main():
    watchlist = load_watchlist()
    cached_versions = load_json(VERSIONS_FILE, {})
    apps = watchlist.get("apps", [])

    if not apps:
        print("Watchlist is leeg.")
        return

    print(f"Controleren van {len(apps)} app(s)...")
    new_rss_items = []
    new_versions = dict(cached_versions)

    for app in apps:
        app_id = str(app["id"])
        print(f"  {app['name']} ({app_id})")
        info = fetch_app_info(app_id)
        if not info:
            print("    Overgeslagen.")
            continue

        latest  = info.get("version", "")
        cached  = cached_versions.get(app_id)
        notes   = info.get("releaseNotes", "")
        url     = f"https://apps.apple.com/nl/app/id{app_id}"

        if not cached:
            new_versions[app_id] = latest
            print(f"    Eerste check: {latest} opgeslagen.")
        elif cached != latest:
            print(f"    UPDATE: {cached} -> {latest}")
            new_versions[app_id] = latest
            new_rss_items.append(make_rss_item(app, latest, cached, notes, url))
        else:
            print(f"    Geen update ({latest}).")

    build_feed(new_rss_items, load_existing_feed_items(FEED_FILE), FEED_FILE)
    save_json(VERSIONS_FILE, new_versions)
    print(f"\nKlaar: {len(new_rss_items)} update(s) gevonden.")

if __name__ == "__main__":
    main()
