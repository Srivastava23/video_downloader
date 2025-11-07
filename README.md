🎥 Reeloader — Multi-Platform Video Downloader

A modern, ad-free, multi-platform video downloader built with Flask, yt-dlp, and a clean Netlify + Render deployment stack.
Download videos or playlists privately — no ads, no tracking, no shady third-party sites.

🚀 Features

✅ Supports YouTube, Instagram, Pinterest, and more
✅ Single video or full playlist downloads
✅ Playlist Analyzer — total duration, count, playback time at custom speeds
✅ Choose Audio / Video / Combined mode
✅ Optional ZIP packaging for full playlists
✅ CORS-secured API with custom key for safe Netlify + Render connection
✅ Fast server-side downloads (no client exposure)
✅ Simple & clean UI — built for personal use

🧱 Project Structure
video_downloader/
│
├─ app.py                 # Flask backend (Render)
├─ requirements.txt       # Python dependencies
├─ counter.json           # Daily download tracker
├─ .render.yaml           # Render deployment config
├─ .gitignore
│
├─ frontend/              # Deployed on Netlify
│   ├─ index.html
│   ├─ style.css
│   ├─ script.js
│   └─ favicon.ico
│
└─ README_DEPLOY.md       # This file

⚙️ Deployment Setup
1️⃣ Backend (Render)

Push this repo to GitHub

Go to Render.com
 → Create New Web Service

Connect your GitHub repo

Render auto-detects Flask and builds automatically

Once deployed, copy your live backend URL — e.g.

https://video-downloader-nbip.onrender.com


Render automatically:

Installs dependencies from requirements.txt

Runs python app.py on port 5000

⚠️ FFmpeg is no longer required.

2️⃣ Frontend (Netlify)

Go to Netlify → Add New Site → Deploy manually

Drag and drop your frontend/ folder

In script.js, make sure BASE_URL points to your Render backend:

const BASE_URL = "https://video-downloader-nbip.onrender.com";


Netlify will deploy instantly at:

https://reeloader.netlify.app

🧾 API Overview
Endpoint	Method	Description
/formats	POST	Fetch available video formats
/playlist_info	POST	Retrieve playlist or single video info
/download	POST	Download selected format (stream or file)

Each request includes:

X-API-KEY: secret123

⚙️ Environment Variables (Render)
Variable	Description	Default
FRONTEND_ORIGIN	Netlify domain	https://reeloader.netlify.app
API_KEY	API key for request auth	secret123
MAX_SIMULTANEOUS	Concurrent downloads limit	2
🧪 Verification Checklist

After deployment:

Open https://reeloader.netlify.app

Paste any YouTube/Instagram link → “Get Formats”

Choose format → “Download”

Paste a playlist → “Playlist Info”

Confirm title, count, thumbnails, durations

Adjust playback speed → recalculates total time

Enable ZIP → downloads all in one file

✅ If all steps pass — your full-stack cloud instance is functional.

📦 Dependencies
Flask
yt-dlp
requests
flask-limiter
flask-cors
werkzeug

🧠 Notes

No local setup needed — just deploy and use.

CORS is locked to your Netlify frontend for security.

Temporary downloads are stored in /tmp on Render and auto-cleaned.

Ad-free, open-source, and optimized for personal or educational use.
