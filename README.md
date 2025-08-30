# YouTube Library by Category

A minimal Streamlit app to catalog YouTube videos in folders, watch them, and take notes.

## Features
- Organize videos in folders.
- Fetch metadata from YouTube oEmbed (optionally YouTube Data API if `YTB_API_KEY` env var is set).
- Watch videos with a side-by-side Markdown note editor.
- Toggle watched/watch-later flags.
- Backup and restore the library JSON.

## Setup
```bash
pip install -r requirements.txt
streamlit run app.py
```

The app stores data in `data_store.json` by default.
