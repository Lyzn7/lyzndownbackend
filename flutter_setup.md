# Lyzndown Flutter Android + Railway Setup

Project Flutter ada di folder `lyzndown_app`. Backend FastAPI tetap di root project dan dipakai sebagai server downloader berbasis `yt-dlp`.

## Backend Lokal

Jalankan backend lokal:

```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

Endpoint utama:

```text
GET /formats?url=<video_url>
GET /download?url=<video_url>&type=mp4&format=<format_id>
GET /download?url=<video_url>&type=mp3
```

Untuk convert MP3, server perlu `ffmpeg`. Di Railway, `ffmpeg` sudah disediakan lewat Dockerfile.

## Deploy Backend Ke Railway

Backend tidak dimasukkan ke APK. Yang di-deploy ke Railway adalah backend Python di root project:

```text
main.py
requirements.txt
Dockerfile
.dockerignore
railway.json
example.env
```

Langkah deploy:

1. Push project ini ke GitHub.
2. Buka Railway.
3. Pilih `New Project`.
4. Pilih `Deploy from GitHub repo`.
5. Pilih repo project ini.
6. Railway akan membaca `railway.json` dan build memakai `Dockerfile`.
7. Buka service backend, masuk ke `Variables`, tambahkan:

```text
ALLOWED_ORIGIN=*
```

Jika YouTube menampilkan error `Sign in to confirm you're not a bot`, tambahkan cookies YouTube untuk `yt-dlp`.

Cara paling aman untuk Railway:

1. Export cookies YouTube dalam format Netscape/Mozilla `cookies.txt`.
2. Jangan commit `cookies.txt` ke GitHub.
3. Encode file cookies ke base64 dari PowerShell:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("cookies.txt"))
```

4. Salin hasil base64.
5. Di Railway `Variables`, tambahkan:

```text
YTDLP_COOKIES_B64=<hasil_base64_cookies_txt>
```

6. Redeploy service Railway.

8. Buka `Settings` lalu `Networking`.
9. Klik `Generate Domain`.
10. Salin domain Railway, contohnya:

```text
https://lyzndown-production.up.railway.app
```

Railway otomatis memberi environment `PORT`. Tidak perlu start command manual karena Dockerfile sudah menjalankan:

```text
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Cek backend setelah deploy:

```text
https://domain-railway-anda.up.railway.app/
https://domain-railway-anda.up.railway.app/formats?url=<video_url>
```

Jika endpoint `/` menampilkan `Lyzndown API`, backend sudah hidup.

## Flutter Android

Install dependency:

```bash
cd lyzndown_app
flutter pub get
```

Run di Android emulator dengan backend lokal:

```bash
flutter run
```

Default API di app adalah:

```text
http://10.0.2.2:8001
```

Run app dengan backend Railway:

```bash
flutter run --dart-define=API_BASE_URL=https://domain-railway-anda.up.railway.app
```

Build APK debug:

```bash
flutter build apk --debug --dart-define=API_BASE_URL=https://domain-railway-anda.up.railway.app
```

Build APK release:

```bash
flutter build apk --release --dart-define=API_BASE_URL=https://domain-railway-anda.up.railway.app
```

## Android Notes

- App hanya dibuat untuk Android.
- Permission `INTERNET` sudah ditambahkan.
- `android:usesCleartextTraffic="true"` aktif agar testing HTTP lokal berjalan. Untuk production HTTPS Railway, opsi ini bisa dimatikan nanti.
- File hasil download disimpan di external app directory Android dan bisa dibuka lewat tombol `Buka File`.
