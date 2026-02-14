# Media Streaming Lab

Flask app to add videos from URLs, convert them, and stream with playlists.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## Deployment

### How to check errors on your deployed site

When you see **Internal Server Error** or videos not converting/playing, check the **server logs** for the real error. How depends on where you host:

| Platform | Where to see logs |
|----------|--------------------|
| **Render** | Dashboard → your service → **Logs** tab. Scroll for Python tracebacks. |
| **Railway** | Project → your service → **Deployments** → click a deployment → **View Logs**. |
| **Heroku** | `heroku logs --tail -a your-app-name` in terminal, or Dashboard → app → **More** → **View logs**. |
| **PythonAnywhere** | **Web** tab → **Error log** and **Server log**. |
| **Fly.io** | `fly logs -a your-app-name` in terminal. |
| **VPS / own server** | Wherever you run the app (e.g. `systemctl status your-app`, or the terminal running `python app.py` or gunicorn). |

Look for lines like:

- `Video convert error: ...` – problem downloading/converting (e.g. bad URL, or yt-dlp/network issue).
- `Stream video error: ...` – problem serving the file (e.g. file missing or path wrong).
- `Save videos error: ...` – problem writing `videos.json` (e.g. read-only filesystem).

### What was fixed for deployment

1. **No ffmpeg required** – Downloads use a single-file format (`best[ext=mp4]/best[ext=webm]/best`) so hosts without ffmpeg can still convert.
2. **Error handling** – Convert and stream errors are caught and logged; the user sees a flash message instead of a raw 500.
3. **Flash messages** – Success/error messages appear at the top of the page after Convert.
4. **SECRET_KEY** – Set `SECRET_KEY` in your host’s environment variables so flash messages work in production.

### Optional env vars

- `SECRET_KEY` – Required for flash messages. Set to a long random string in production.
- `PORT` – Many hosts set this automatically (e.g. Render, Heroku, Railway).

### Railway / reverse proxy

The app uses **ProxyFix** so Flask trusts `X-Forwarded-*` headers. That keeps the session cookie working behind Railway’s HTTPS proxy (login and Convert no longer redirect to the login page).

### Note on free hosts

Many free tiers use an **ephemeral filesystem**: `downloads/`, `videos.json`, and `playlists.json` can be wiped on restart or redeploy. For persistent storage you’d need a database and object storage (e.g. S3) instead of local files.

---

## Offline support (PWA)

The app uses a **service worker with offline caching** so it can work without internet for content you’ve already loaded.

### Your four options (and which we use)

| Option | What it means | Best for this app? |
|--------|----------------|---------------------|
| **1. Load local HTML/CSS/JS** | Serve the UI from local files instead of the server. | No – your app is server-rendered (Flask templates) and needs the backend for login, videos, playlists. |
| **2. Service worker + offline caching (PWA)** | Cache pages and media in the browser; when offline, serve from cache. | **Yes – implemented.** Simplest way to get offline for an existing Flask app. |
| **3. Package assets in an Android app** | Build a native Android app (e.g. WebView) that bundles the site. | No – more work, separate codebase, and you still need the backend for data. |
| **4. Cache data for offline** | Store API/data in IndexedDB or cache layer for offline use. | Part of option 2 – we cache full HTML and video responses so “data” is the cached pages and files. |

**Best and simplest for full offline:** **Option 2 (PWA + service worker)**, which is already in place.

### What works offline

- **Login page** – Precached; opens even when offline.
- **Main app (home)** – If you’ve opened it once while online, the last version is shown from cache when offline.
- **Videos you’ve already played** – Cached; you can play them again without internet.
- **Manifest and icon** – Cached so “Add to Home Screen” and app icon work.

### What still needs internet

- **Logging in** (first time or after logout) – Server checks credentials.
- **Converting new videos** – Server runs yt-dlp.
- **Creating/editing playlists** – Saved on the server.
- **First load of a page** – Must hit the server once; after that it’s cached.

So: **offline = use the last cached version of the app and cached videos**. New actions (login, convert, add playlist) require connection.
