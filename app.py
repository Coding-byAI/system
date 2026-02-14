from flask import Flask, render_template, request, send_from_directory, redirect, flash, session
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import yt_dlp
import os
import json
import uuid
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
# Session ends when browser/app is closed (session cookie, no long-lived expiry)
app.config["SESSION_PERMANENT"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = 0
# Ensure session cookie is sent with same-site form POST (e.g. Convert button)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_PATH"] = "/"

# Paths relative to app folder so they work no matter where the app is run from
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, "downloads")
DATA_FILE = os.path.join(BASE_DIR, "videos.json")
PLAYLIST_FILE = os.path.join(BASE_DIR, "playlists.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
MAX_USERS = 3

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# ------------------ LOAD USERS ------------------

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return []

def save_users(users_list):
    with open(USERS_FILE, "w") as f:
        json.dump(users_list, f, indent=4)

users = load_users()

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

# ------------------ AUTH HELPERS ------------------

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get("user_id") is None:
            flash("Please log in to continue.", "error")
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapped

def get_current_user_id():
    return session.get("user_id")

def get_user_videos():
    uid = get_current_user_id()
    return [v for v in videos if v.get("user_id") == uid]

def get_user_playlists():
    uid = get_current_user_id()
    return [p for p in playlists if p.get("user_id") == uid]

# ------------------ AUTH ROUTES ------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    global users
    users = load_users()
    if session.get("user_id") is not None:
        return redirect("/")
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect("/login")
        for u in users:
            if (u.get("username") or "").lower() == username.lower():
                if check_password_hash(u.get("password", ""), password):
                    session["user_id"] = u["id"]
                    session["username"] = u["username"]  # use stored username (correct casing)
                    return redirect("/")
                flash("Password incorrect.", "error")
                return redirect("/login")
        flash("Username not found.", "error")
        return redirect("/login")
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    global users
    users = load_users()
    if session.get("user_id") is not None:
        return redirect("/")
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect("/signup")
        if len(users) >= MAX_USERS:
            flash("Maximum users reached (3 only). Registration is closed.", "error")
            return redirect("/signup")
        for u in users:
            if (u.get("username") or "").lower() == username.lower():
                flash("Username already exists.", "error")
                return redirect("/signup")
        user_id = str(uuid.uuid4())
        users.append({
            "id": user_id,
            "username": username,
            "password": generate_password_hash(password),
        })
        save_users(users)
        session["user_id"] = user_id
        session["username"] = username
        return redirect("/")
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/delete_account", methods=["POST"])
@login_required
def delete_account():
    global users, videos, playlists
    uid = get_current_user_id()
    # Delete all video files belonging to this user
    for v in list(videos):
        if v.get("user_id") == uid:
            file_path = os.path.join(DOWNLOAD_FOLDER, v.get("filename", ""))
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.exception("Delete video file error: %s", e)
    # Remove user's videos and playlists from data
    videos = [v for v in videos if v.get("user_id") != uid]
    playlists = [p for p in playlists if p.get("user_id") != uid]
    users = [u for u in load_users() if u.get("id") != uid]
    save_videos()
    save_playlists()
    save_users(users)
    session.clear()
    flash("Account deleted. You can sign up again.", "success")
    return redirect("/login")

# ------------------ PROTECTED ROUTES ------------------

@app.route("/", methods=["GET", "POST"])
@login_required
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
            "user_id": get_current_user_id(),
        }
        videos.append(video_data)
        save_videos()
        flash("Video added successfully.", "success")

    return render_template(
        "index.html",
        videos=get_user_videos(),
        playlists=get_user_playlists(),
        username=session.get("username"),
    )

@app.route("/video/<path:filename>")
@login_required
def stream_video(filename):
    uid = get_current_user_id()
    for v in videos:
        if v.get("user_id") == uid and v.get("filename") == filename:
            try:
                return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=False)
            except Exception as e:
                logger.exception("Stream video error: %s", e)
                return f"Video not found: {filename}", 404
    return "Forbidden", 403

@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")

@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js"), 200, {"Content-Type": "application/javascript"}

@app.route("/icon.png")
def app_icon():
    """Serve icon 1.png from system folder for PWA and apple-touch-icon."""
    path = os.path.join(app.root_path, "icon 1.png")
    if not os.path.isfile(path):
        return "Icon not found", 404
    return send_from_directory(app.root_path, "icon 1.png", mimetype="image/png")

@app.route("/create_playlist", methods=["POST"])
@login_required
def create_playlist():
    name = request.form.get("name", "").strip()
    if not name:
        return redirect("/")
    playlists.append({
        "id": str(uuid.uuid4()),
        "name": name,
        "songs": [],
        "user_id": get_current_user_id(),
    })
    save_playlists()
    return redirect("/")

@app.route("/add_to_playlist", methods=["POST"])
@login_required
def add_to_playlist():
    playlist_id = request.form.get("playlist_id")
    video_id = request.form.get("video_id")
    uid = get_current_user_id()
    for p in playlists:
        if p.get("user_id") == uid and p["id"] == playlist_id:
            if video_id not in p["songs"]:
                p["songs"].append(video_id)
            break
    save_playlists()
    return redirect("/")

@app.route("/delete_playlist/<playlist_id>")
@login_required
def delete_playlist(playlist_id):
    global playlists
    uid = get_current_user_id()
    playlists = [p for p in playlists if not (p.get("user_id") == uid and p["id"] == playlist_id)]
    save_playlists()
    return redirect("/")

@app.route("/rename_playlist/<playlist_id>", methods=["POST"])
@login_required
def rename_playlist(playlist_id):
    new_name = (request.form.get("new_name") or "").strip()
    uid = get_current_user_id()
    for p in playlists:
        if p.get("user_id") == uid and p["id"] == playlist_id:
            p["name"] = new_name
            break
    save_playlists()
    return redirect("/")

@app.route("/delete_video/<video_id>")
@login_required
def delete_video(video_id):
    global videos, playlists
    uid = get_current_user_id()

    video_to_delete = None
    for v in videos:
        if v.get("id") == video_id and v.get("user_id") == uid:
            video_to_delete = v
            break

    if video_to_delete:
        file_path = os.path.join(DOWNLOAD_FOLDER, video_to_delete["filename"])
        if os.path.exists(file_path):
            os.remove(file_path)
        videos = [v for v in videos if v.get("id") != video_id]
        save_videos()
        for p in playlists:
            if video_id in p.get("songs", []):
                p["songs"].remove(video_id)
        save_playlists()

    return redirect("/")

@app.route("/playlist/<playlist_id>")
@login_required
def view_playlist(playlist_id):
    uid = get_current_user_id()
    selected_playlist = None
    for p in playlists:
        if p.get("user_id") == uid and p["id"] == playlist_id:
            selected_playlist = p
            break
    if not selected_playlist:
        return redirect("/")
    playlist_videos = [v for v in videos if v.get("user_id") == uid and v.get("id") in selected_playlist.get("songs", [])]
    return render_template(
        "index.html",
        videos=playlist_videos,
        playlists=get_user_playlists(),
        active_playlist=selected_playlist,
        username=session.get("username"),
    )

# ------------------ RUN APP ------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))