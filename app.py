from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
import requests
from dotenv import load_dotenv
from uuid import uuid4

app = Flask(__name__)
load_dotenv()

STORY_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(STORY_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'webm', 'ogg', 'mkv'}

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME', ''),
    api_key=os.getenv('CLOUDINARY_API_KEY', ''),
    api_secret=os.getenv('CLOUDINARY_API_SECRET', '')
)

GOOGLE_SCRIPT_URL = os.getenv('GOOGLE_SCRIPT_URL', '')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'mrshaik')


# ---------------- ALLOWED FILE CHECK ----------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------- LOG TO GOOGLE SCRIPT ----------------
def log_event(ip, event, password='', chat='', story_url='', reels_url=''):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "timestamp": timestamp,
        "ip": ip,
        "event": event,
        "password": password,
        "chat": chat,
        "story_url": story_url,
        "reels_url": reels_url
    }

    try:
        requests.post(GOOGLE_SCRIPT_URL, json=payload)
    except:
        print("Error sending data to Google Script")


# -------------- FETCH LATEST STORY / REEL ----------------
def fetch_from_gsheet(query):
    """Helper to fetch any record from GAS."""
    try:
        resp = requests.get(GOOGLE_SCRIPT_URL + query, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return {}


# -------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/main')
def main():
    return render_template('main.html')

@app.route('/SHAIK')
def SHAIK():
    return render_template('SHAIK.html')

# ---------------- PASSWORD CHECK ----------------
@app.route('/save_password', methods=['POST'])
def save_password():
    data = request.get_json() or {}
    password = data.get("password", "")
    ip = request.remote_addr

    log_event(ip, "password_attempt", password=password)

    if password == ADMIN_PASSWORD:
        return jsonify({"redirect": "/main"})
    return jsonify({"message": "Incorrect password!"}), 401


# ---------------- STORY UPLOAD ----------------
@app.route('/upload_story_video', methods=['POST'])
def upload_story_video():

    if 'video' not in request.files:
        return "No file", 400

    file = request.files['video']
    if not file.filename:
        return "No filename", 400

    uploader = request.form.get('uploader', 'user')
    ip = request.remote_addr

    if not allowed_file(file.filename):
        return "Unsupported file", 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    unique = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex}.{ext}"
    local_path = os.path.join(STORY_FOLDER, unique)
    file.save(local_path)

    try:
        with open(local_path, "rb") as f:
            upload = cloudinary.uploader.upload_large(f, resource_type="video", folder="stories")
        video_url = upload.get("secure_url", "")
    except:
        video_url = url_for("uploaded_file", filename=unique, _external=True)

    event = "admin_story_upload" if uploader == "admin" else "user_story_upload"
    log_event(ip, event, story_url=video_url)

    return redirect(url_for('main'))


# ---------------- REELS UPLOAD ----------------
# ---------------- REELS UPLOAD (OPTIMIZED) ----------------
@app.route('/userupload_reels', methods=['POST'])
def userupload_reels():

    if 'video' not in request.files:
        return "No file", 400

    file = request.files['video']
    if not file.filename:
        return "No filename", 400

    ip = request.remote_addr

    if not allowed_file(file.filename):
        return "Invalid file", 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    unique = f"reel_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex}.{ext}"

    local_path = os.path.join(STORY_FOLDER, unique)
    file.save(local_path)

    try:
        with open(local_path, "rb") as fobj:
            up = cloudinary.uploader.upload_large(
                fobj,
                resource_type="video",
                folder="user_reels",
                eager=[{
                    "format": "mp4",
                    "quality": "auto:eco",  # low data, good quality
                    "width": 720,           # balance of size & quality
                    "video_codec": "h264"
                }]
            )

        # ⭐ Use the optimized mp4 URL
        video_url = up["eager"][0]["secure_url"]

        # Optional: HLS adaptive streaming (loads in chunks, very low data)
        # hls_url = cloudinary.CloudinaryVideo(up['public_id']).build_url(
        #     resource_type="video",
        #     streaming_profile="mobile",
        #     format="m3u8"
        # )
        # video_url = hls_url

    except Exception as e:
        print("Cloudinary upload failed:", e)
        # fallback to local URL if Cloudinary fails
        video_url = url_for("uploaded_file", filename=unique, _external=True)

    log_event(ip, "user_reels_upload", reels_url=video_url)

    return redirect(url_for('SHAIK'))



# ---------------- VIEW PAGES ----------------



# ---------------- GET LATEST STORIES ----------------
@app.route('/last_admin_story')
def last_admin_story():
    data = fetch_from_gsheet("?mode=latest&story=admin")
    return jsonify({"url": data.get("story_url", "")})


@app.route('/last_user_story')
def last_user_story():
    data = fetch_from_gsheet("?mode=latest&story=user")
    return jsonify({"url": data.get("story_url", "")})


# ---------------- GET LATEST REEL ----------------
@app.route('/last_user_reels')
def last_user_reels():
    data = fetch_from_gsheet("?mode=latest&story=reels")
    return jsonify({"url": data.get("reels_url", "")})


# ---------------- GET ALL REELS FOR INSTA VIEW ----------------
@app.route('/all_user_reels')
def all_user_reels():
    data = fetch_from_gsheet("?mode=all_reels")
    return jsonify({"urls": data.get("urls", [])})


# ---------------- LOCAL FILE SERVE ----------------
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(STORY_FOLDER, filename)


# ---------------- RUN APP ----------------
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=False)

