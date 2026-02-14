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
- `PORT` – Many hosts set this automatically (e.g. Render, Heroku).

### Note on free hosts

Many free tiers use an **ephemeral filesystem**: `downloads/`, `videos.json`, and `playlists.json` can be wiped on restart or redeploy. For persistent storage you’d need a database and object storage (e.g. S3) instead of local files.
