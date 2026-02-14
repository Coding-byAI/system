from flask import Flask, render_template, request, send_from_directory, redirect
import yt_dlp
import os
import json
import uuid

app = Flask(__name__)

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
    with open(DATA_FILE, "w") as f:
        json.dump(videos, f, indent=4)

def save_playlists():
    with open(PLAYLIST_FILE, "w") as f:
        json.dump(playlists, f, indent=4)

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
        url = request.form["url"]

        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
            'merge_output_format': 'mp4',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            filename = os.path.splitext(filename)[0] + ".mp4"

        video_data = {
            "id": str(uuid.uuid4()),
            "title": info['title'],
            "thumbnail": info['thumbnail'],
            "filename": os.path.basename(filename)
        }

        videos.append(video_data)
        save_videos()

    return render_template("index.html", videos=videos, playlists=playlists)

@app.route("/video/<filename>")
def stream_video(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename)

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
    app.run(debug=True)
