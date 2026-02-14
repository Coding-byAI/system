from flask import Flask, render_template, request, send_from_directory, redirect, flash
import yt_dlp
import os
import json
import uuid
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

DOWNLOAD_FOLDER = "downloads"
DATA_FILE = "videos.json"
PLAYLIST_FILE = "playlists.json"

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# ------------------ LOAD VIDEOS ------------------

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        videos = json.load(f)
else:
    videos = []

# ------------------ LOAD PLAYLISTS ------------------

if os.path.exists(PLAYLIST_FILE):
    with open(PLAYLIST_FILE, "r") as f:
        playlists = json.load(f)
else:
    playlists = []

# ------------------ SAVE FUNCTIONS ------------------

def save_videos():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(videos, f, indent=4)
    except Exception as e:
        logger.exception("Save videos error: %s", e)
        raise

def save_playlists():
    try:
        with open(PLAYLIST_FILE, "w") as f:
            json.dump(playlists, f, indent=4)
    except Exception as e:
        logger.exception("Save playlists error: %s", e)
        raise

# ------------------ DATA MIGRATION FIX ------------------
# Add ID automatically if missing (for old videos)

updated = False
for v in videos:
    if "id" not in v:
        v["id"] = str(uuid.uuid4())
        updated = True

if updated:
    save_videos()

# ------------------ ROUTES ------------------

@app.route("/", methods=["GET", "POST"])
def index():
    global videos

    if request.method == "POST":
        url = (request.form.get("url") or "").strip()
        if not url:
            flash("Please enter a video URL.", "error")
            return redirect("/")

        # Use format that works without ffmpeg on most hosts (single file, no merge)
        ydl_opts = {
            "format": "best[ext=mp4]/best[ext=webm]/best",
            "outtmpl": f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
            "noplaylist": True,
            "quiet": False,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    flash("Could not get video info. Check the URL.", "error")
                    return redirect("/")
                filename = ydl.prepare_filename(info)
                if not os.path.exists(filename):
                    flash("Download failed: file was not created.", "error")
                    return redirect("/")
        except Exception as e:
            err_msg = str(e)
            logger.exception("Video convert error: %s", err_msg)
            flash(f"Convert failed: {err_msg}", "error")
            return redirect("/")

        ext = os.path.splitext(filename)[1].lower()
        mime = "video/webm" if ext == ".webm" else "video/mp4"
        video_data = {
            "id": str(uuid.uuid4()),
            "title": info.get("title", "Unknown"),
            "thumbnail": info.get("thumbnail") or "",
            "filename": os.path.basename(filename),
            "mime": mime,
        }
        videos.append(video_data)
        save_videos()
        flash("Video added successfully.", "success")

    return render_template("index.html", videos=videos, playlists=playlists)

@app.route("/video/<path:filename>")
def stream_video(filename):
    try:
        return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=False)
    except Exception as e:
        logger.exception("Stream video error: %s", e)
        return f"Video not found: {filename}", 404

@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")

@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js"), 200, {"Content-Type": "application/javascript"}

@app.route("/create_playlist", methods=["POST"])
def create_playlist():
    name = request.form["name"]

    playlists.append({
        "id": str(uuid.uuid4()),
        "name": name,
        "songs": []
    })

    save_playlists()
    return redirect("/")

@app.route("/add_to_playlist", methods=["POST"])
def add_to_playlist():
    playlist_id = request.form["playlist_id"]
    video_id = request.form["video_id"]

    for p in playlists:
        if p["id"] == playlist_id:
            if video_id not in p["songs"]:
                p["songs"].append(video_id)

    save_playlists()
    return redirect("/")

@app.route("/delete_playlist/<playlist_id>")
def delete_playlist(playlist_id):
    global playlists
    playlists = [p for p in playlists if p["id"] != playlist_id]
    save_playlists()
    return redirect("/")

@app.route("/rename_playlist/<playlist_id>", methods=["POST"])
def rename_playlist(playlist_id):
    new_name = request.form["new_name"]

    for p in playlists:
        if p["id"] == playlist_id:
            p["name"] = new_name

    save_playlists()
    return redirect("/")

@app.route("/delete_video/<video_id>")
def delete_video(video_id):
    global videos, playlists

    video_to_delete = None
    for v in videos:
        if v.get("id") == video_id:
            video_to_delete = v
            break

    if video_to_delete:
        file_path = os.path.join(DOWNLOAD_FOLDER, video_to_delete["filename"])
        if os.path.exists(file_path):
            os.remove(file_path)

        videos = [v for v in videos if v.get("id") != video_id]
        save_videos()

        for p in playlists:
            if video_id in p["songs"]:
                p["songs"].remove(video_id)

        save_playlists()

    return redirect("/")
@app.route("/playlist/<playlist_id>")
def view_playlist(playlist_id):
    selected_playlist = None

    for p in playlists:
        if p["id"] == playlist_id:
            selected_playlist = p
            break

    if not selected_playlist:
        return redirect("/")

    # Filter videos that belong to this playlist
    playlist_videos = [v for v in videos if v.get("id") in selected_playlist["songs"]]

    return render_template(
        "index.html",
        videos=playlist_videos,
        playlists=playlists,
        active_playlist=selected_playlist
    )

# ------------------ RUN APP ------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))