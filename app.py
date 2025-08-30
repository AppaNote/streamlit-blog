"""Streamlit YouTube Library app."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import requests
import streamlit as st
from urllib.parse import parse_qs, urlparse

DATA_FILE = "data_store.json"

# ---------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------

def load_store() -> Dict:
    """Read JSON data from disk."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"categories": {}}


def save_store(store: Dict) -> None:
    """Persist JSON data to disk."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


def ensure_category(store: Dict, name: str) -> None:
    """Create a category if missing."""
    store.setdefault("categories", {})
    store["categories"].setdefault(name, {"videos": [], "notes": ""})


def add_category(store: Dict, name: str) -> None:
    """Add a new folder."""
    ensure_category(store, name)
    save_store(store)


def add_video(store: Dict, category: str, data: Dict) -> None:
    """Append a video to a category."""
    ensure_category(store, category)
    store["categories"][category]["videos"].append(data)
    save_store(store)


def find_video(store: Dict, cat: str, vid: str) -> Optional[Dict]:
    """Return video dict by id."""
    for v in store["categories"].get(cat, {}).get("videos", []):
        if v["id"] == vid:
            return v
    return None


def update_video(store: Dict, cat: str, vid: str, updates: Dict) -> None:
    """Update fields for a video."""
    video = find_video(store, cat, vid)
    if video:
        video.update(updates)
        save_store(store)


def move_video(store: Dict, src: str, dst: str, vid: str) -> None:
    """Move video between folders."""
    video = find_video(store, src, vid)
    if not video:
        return
    store["categories"][src]["videos"] = [v for v in store["categories"][src]["videos"] if v["id"] != vid]
    ensure_category(store, dst)
    store["categories"][dst]["videos"].append(video)
    save_store(store)


def delete_video(store: Dict, cat: str, vid: str) -> None:
    """Remove a video from a folder."""
    vids = store["categories"].get(cat, {}).get("videos", [])
    store["categories"][cat]["videos"] = [v for v in vids if v["id"] != vid]
    save_store(store)


def search_videos(store: Dict, query: str) -> List[Dict]:
    """Return videos matching query across categories."""
    results = []
    q = query.lower()
    for cat, data in store["categories"].items():
        for v in data["videos"]:
            hay = " ".join(
                [v.get("title", ""), v.get("channel", ""), " ".join(v.get("tags", [])), v.get("notes", ""), v.get("url", ""), cat]
            ).lower()
            if q in hay:
                results.append((cat, v))
    return results


# ---------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------

def youtube_id_from_url(url: str) -> Optional[str]:
    """Extract video id from YouTube URL."""
    try:
        parsed = urlparse(url)
        if parsed.netloc in {"youtu.be"}:
            return parsed.path.lstrip("/")
        if "watch" in parsed.path:
            return parse_qs(parsed.query).get("v", [None])[0]
        if "shorts" in parsed.path or "embed" in parsed.path:
            return parsed.path.split("/")[-1]
    except Exception:
        return None
    return None


def get_oembed(url: str) -> Dict:
    """Fetch basic metadata via oEmbed."""
    resp = requests.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_youtube_api_details(video_id: str, api_key: str) -> Dict:
    """Optional call to YouTube Data API v3."""
    endpoint = "https://www.googleapis.com/youtube/v3/videos"
    params = {"part": "contentDetails,snippet", "id": video_id, "key": api_key}
    resp = requests.get(endpoint, params=params, timeout=10)
    resp.raise_for_status()
    items = resp.json().get("items")
    if not items:
        return {}
    item = items[0]
    return {
        "duration": item.get("contentDetails", {}).get("duration"),
        "published_at": item.get("snippet", {}).get("publishedAt"),
        "description": item.get("snippet", {}).get("description"),
    }


def fetch_metadata(url: str) -> Dict:
    """Fetch metadata combining oEmbed and optional API."""
    data = get_oembed(url)
    video_id = youtube_id_from_url(url)
    meta = {
        "id": video_id,
        "url": url,
        "title": data.get("title"),
        "channel": data.get("author_name"),
        "thumbnail_url": data.get("thumbnail_url"),
    }
    api_key = os.getenv("YTB_API_KEY")
    if api_key and video_id:
        try:
            more = get_youtube_api_details(video_id, api_key)
            meta.update(more)
        except Exception:
            pass
    return meta


# ---------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------

def show_add_folder(store: Dict) -> None:
    """Modal to add new folder."""
    with st.form("add_folder"):
        name = st.text_input("Folder name")
        submitted = st.form_submit_button("Save")
        if submitted and name:
            if name in store["categories"]:
                st.warning("Folder exists")
            else:
                add_category(store, name)
                st.success("Folder added")
                st.experimental_rerun()


def show_add_video(store: Dict) -> None:
    """Modal to add a video."""
    with st.form("add_video", clear_on_submit=False):
        url = st.text_input("YouTube URL", key="video_url")
        folder = st.selectbox("Folder", list(store["categories"].keys()))
        if st.form_submit_button("Fetch metadata") and url:
            try:
                st.session_state.meta = fetch_metadata(url)
            except Exception as e:
                st.error(f"Fetch failed: {e}")
        meta = st.session_state.get("meta", {})
        title = st.text_input("Title", meta.get("title", ""))
        channel = st.text_input("Channel", meta.get("channel", ""))
        tags = st.text_input("Tags (comma)", ",".join(meta.get("tags", [])))
        if st.form_submit_button("Save video"):
            if not url:
                st.warning("URL required")
            else:
                data = {
                    "id": meta.get("id") or youtube_id_from_url(url),
                    "url": url,
                    "title": title,
                    "channel": channel,
                    "duration": meta.get("duration"),
                    "published_at": meta.get("published_at"),
                    "description": meta.get("description"),
                    "tags": [t.strip() for t in tags.split(",") if t.strip()],
                    "watch_later": False,
                    "watched": False,
                    "notes": "",
                    "thumbnail_url": meta.get("thumbnail_url"),
                    "added_at": datetime.utcnow().isoformat(),
                }
                add_video(store, folder, data)
                st.success("Video added")
                st.session_state.pop("meta", None)
                st.experimental_rerun()


def show_video_player(cat: str, video: Dict) -> None:
    """Display video with notes editor."""
    st.subheader(video.get("title"))
    vid = video["id"]
    quality = st.selectbox("Quality", ["highres", "hd1080", "hd720", "large", "medium"], index=0, key=f"q_{vid}")
    player_html = f"""
    <iframe id="player" type="text/html" width="100%" height="360"
        src="https://www.youtube.com/embed/{vid}?enablejsapi=1&autoplay=1"
        frameborder="0"></iframe>
    <script>
    var tag = document.createElement('script');
    tag.src = "https://www.youtube.com/iframe_api";
    var firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
    function onYouTubeIframeAPIReady(){{
        var player = new YT.Player('player', {{events: {{'onReady': onPlayerReady}}}});
    }}
    function onPlayerReady(event){{
        event.target.setPlaybackQuality('{quality}');
    }}
    </script>
    """
    st.components.v1.html(player_html, height=400)
    notes = st.text_area("Notes", video.get("notes", ""), height=200, key=f"notes_{vid}")
    if st.button("Save notes", key=f"save_{vid}"):
        update_video(store, cat, vid, {"notes": notes})
        st.success("Saved")


def video_card(store: Dict, cat: str, video: Dict) -> None:
    """Render a single video card."""
    with st.container(border=True):
        st.image(video.get("thumbnail_url"))
        st.caption(video.get("channel"))
        st.write(video.get("title"))
        cols = st.columns(4)
        if cols[0].button("Watch", key=f"watch_{video['id']}"):
            st.session_state.current = (cat, video["id"])
        if cols[1].button("Watched" if video.get("watched") else "Unwatched", key=f"toggle_w_{video['id']}"):
            update_video(store, cat, video["id"], {"watched": not video.get("watched")})
            st.experimental_rerun()
        if cols[2].button("Later" if video.get("watch_later") else "Add later", key=f"toggle_l_{video['id']}"):
            update_video(store, cat, video["id"], {"watch_later": not video.get("watch_later")})
            st.experimental_rerun()
        if cols[3].button("Delete", key=f"del_{video['id']}"):
            delete_video(store, cat, video["id"])
            st.experimental_rerun()


def show_library(store: Dict, active_cat: str, query: str) -> None:
    """Render main grid of videos."""
    videos = []
    if query:
        videos = [v for _, v in search_videos(store, query)]
    else:
        videos = store["categories"].get(active_cat, {}).get("videos", [])
    for i, video in enumerate(videos):
        cols = st.columns(3)
        cols[i % 3].container()
        with cols[i % 3]:
            video_card(store, active_cat, video)


# ---------------------------------------------------------------------
# App layout
# ---------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="YouTube Library", layout="wide")
    store = load_store()

    st.sidebar.title("Folders")
    folders = list(store.get("categories", {}).keys())
    if not folders:
        st.sidebar.info("Add a folder to start")
        active_cat = ""
    else:
        active_cat = st.sidebar.selectbox("Select folder", folders)
    query = st.sidebar.text_input("Search")
    if st.sidebar.button("Backup JSON"):
        st.sidebar.download_button("Download", data=json.dumps(store), file_name="backup.json")
    uploaded = st.sidebar.file_uploader("Restore JSON")
    if uploaded:
        try:
            store = json.load(uploaded)
            save_store(store)
            st.sidebar.success("Restored")
        except Exception:
            st.sidebar.error("Invalid JSON")

    if st.button("Add Folder"):
        show_add_folder(store)
    if st.button("Add Video"):
        show_add_video(store)

    if "current" in st.session_state:
        cat, vid = st.session_state.current
        video = find_video(store, cat, vid)
        if video:
            show_video_player(cat, video)
        if st.button("Back"):
            st.session_state.pop("current")
            st.experimental_rerun()
    else:
        show_library(store, active_cat, query)


if __name__ == "__main__":
    main()
