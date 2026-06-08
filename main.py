import base64
import os
import uuid
import re
import tempfile
import unicodedata
from urllib.parse import quote
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
from dotenv import load_dotenv

app = FastAPI()

# Load environment variables from .env file
load_dotenv()

allowed_origin = os.getenv("ALLOWED_ORIGIN", "*")
allowed_origins = ["*"] if allowed_origin == "*" else [allowed_origin]
_cookies_file_path = None

# CORS configuration
app.add_middleware(CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allowed_origin != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

def cookies_file_path() -> str | None:
    global _cookies_file_path

    configured_path = os.getenv("YTDLP_COOKIES_PATH")
    if configured_path:
        return configured_path

    cookies_b64 = os.getenv("YTDLP_COOKIES_B64")
    if not cookies_b64:
        return None

    if _cookies_file_path:
        return _cookies_file_path

    _cookies_file_path = os.path.join(tempfile.gettempdir(), "yt-dlp-cookies.txt")
    with open(_cookies_file_path, "wb") as file:
        file.write(base64.b64decode(cookies_b64))
    return _cookies_file_path

def clean_url(url: str) -> str:
    return url.strip()

def is_tiktok_url(url: str) -> bool:
    return "tiktok.com" in url

def request_headers(url: str) -> dict:
    if not is_tiktok_url(url):
        return {}
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    }

def info_options(url: str) -> dict:
    options = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "socket_timeout": 30,
    }
    headers = request_headers(url)
    if headers:
        options["http_headers"] = headers
    cookie_file = cookies_file_path()
    if cookie_file:
        options["cookiefile"] = cookie_file
    return options

def safe_title(title: str | None) -> str:
    cleaned = re.sub(r"[^\w\s\-._]", "", title or "video", flags=re.UNICODE)
    cleaned = cleaned.replace("/", "-").replace("\\", "-").strip()
    return cleaned or "video"

def ascii_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFKD", filename)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_only = re.sub(r'[^A-Za-z0-9 ._\-()]', "", ascii_only).strip()
    return ascii_only or "download"

def download_options(url: str, output_template: str, media_type: str, format_id: str) -> dict:
    headers = request_headers(url)
    options = {
        "format": format_id,
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "skip_unavailable_fragments": True,
        "noprogress": True,
    }
    if headers:
        options["http_headers"] = headers
        options["extractor_args"] = {"tiktok": {"api": "mobile"}}
    cookie_file = cookies_file_path()
    if cookie_file:
        options["cookiefile"] = cookie_file

    if media_type == "mp3":
        options["format"] = "bestaudio/best"
        options["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        options["merge_output_format"] = "mp4"
    return options

@app.get("/formats")
async def get_formats(url: str = Query(...)):
    try:
        url = clean_url(url)
        with yt_dlp.YoutubeDL(info_options(url)) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        seen = set()
        for item in info.get("formats", []):
            height = item.get("height")
            format_id = item.get("format_id")
            ext = item.get("ext")
            if not height or not format_id or ext not in {"mp4", "webm"}:
                continue
            key = (height, ext)
            if key in seen:
                continue
            seen.add(key)
            formats.append({
                "format_id": f"{format_id}+bestaudio/best",
                "label": f"{height}p",
                "height": height,
                "ext": ext,
            })

        formats.sort(key=lambda value: value["height"])
        return {
            "title": info.get("title", "Video"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "formats": formats,
            "default_format": "best[ext=mp4]/best",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading formats: {str(e)}")

@app.get("/download")
async def download_video(
    url: str = Query(...),
    format: str = Query("best[ext=mp4]/best"),
    type: str = Query("mp4"),
):
    try:
        url = clean_url(url)
        media_type = type.lower()
        if media_type not in {"mp4", "mp3"}:
            raise HTTPException(status_code=400, detail="type must be mp4 or mp3.")

        with yt_dlp.YoutubeDL(info_options(url)) as ydl:
            info = ydl.extract_info(url, download=False)
            title = safe_title(info.get("title"))
            extension = "mp3" if media_type == "mp3" else "mp4"
            filename = f"{title}.{extension}"

        # Create a unique output template
        uid = uuid.uuid4().hex[:8]
        temp_dir = tempfile.gettempdir()
        output_template = os.path.join(temp_dir, f"{uid}.%(ext)s")

        # Download the video
        with yt_dlp.YoutubeDL(download_options(url, output_template, media_type, format)) as ydl:
            ydl.download([url])

        # Find actual downloaded file
        actual_file_path = None
        for f in os.listdir(temp_dir):
            if f.startswith(uid):
                actual_file_path = os.path.join(temp_dir, f)
                break

        if not actual_file_path or not os.path.exists(actual_file_path):
            raise HTTPException(status_code=500, detail="Download failed or file not found.")

        # Stream file
        def iterfile():
            with open(actual_file_path, "rb") as f:
                yield from f
            os.unlink(actual_file_path)  # clean up after stream

        # URL-encode filename for proper handling
        safe_filename = quote(filename, safe='.-_')
        fallback_filename = ascii_filename(filename)
        
        return StreamingResponse(
            iterfile(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=\"{fallback_filename}\"; "
                    f"filename*=UTF-8''{safe_filename}"
                )
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during download: {str(e)}")

@app.get("/")
async def root():
    return {
        "message": "Lyzndown API",
        "formats": "/formats?url=<video_url>",
        "download": "/download?url=<video_url>&type=mp4|mp3&format=<video_format>",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8001")))
