"""Telecharge un VOD Kick, choisit les N moments les plus bruyants (reactions),
les decoupe en 9:16 avec fond flou, ajoute des sous-titres arabes et ecrit les captions.

Option manuelle : cree un fichier clips.json a cote de ce script, ex :
[{"start": "00:12:30"}, {"start": "00:47:05"}]   (duree = CLIP_SEC)
"""
import os, json, subprocess
import numpy as np

URL = os.environ["VOD_URL"]
N = int(os.environ.get("N_CLIPS", "10"))
DUR = int(os.environ.get("CLIP_SEC", "35"))
os.makedirs("clips", exist_ok=True)


def run(cmd):
    subprocess.run(cmd, check=True)


def hms(s):
    s = int(s)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


def parse(t):
    h, m, s = [int(x) for x in t.split(":")]
    return h * 3600 + m * 60 + s


# 1) Telechargement
if not os.path.exists("vod.mp4"):
    r = subprocess.run(["yt-dlp", "-f", "bv*[height<=720]+ba/b[height<=720]/b",
                        "--merge-output-format", "mp4", "-o", "vod.mp4", URL])
    if r.returncode != 0 and os.environ.get("M3U8"):
        print("yt-dlp a echoue, essai direct du flux m3u8")
        run(["ffmpeg", "-y", "-i", os.environ["M3U8"], "-c", "copy", "vod.mp4"])

# 2) Choix des moments
if os.path.exists("clips.json"):
    starts = [parse(c["start"]) for c in json.load(open("clips.json"))][:N]
else:
    run(["ffmpeg", "-y", "-i", "vod.mp4", "-vn", "-ac", "1", "-ar", "8000",
         "-f", "s16le", "audio.raw"])
    a = np.fromfile("audio.raw", dtype=np.int16).astype(np.float32) / 32768
    sec = len(a) // 8000
    rms = np.sqrt((a[: sec * 8000].reshape(sec, 8000) ** 2).mean(axis=1))
    win = np.convolve(rms, np.ones(DUR) / DUR, mode="valid")
    picks = []
    for i in np.argsort(win)[::-1]:
        if i < 300:  # ignorer les 5 premieres minutes
            continue
        if all(abs(int(i) - p) >= 120 for p in picks):
            picks.append(int(i))
        if len(picks) == N:
            break
    starts = sorted(max(0, p - 3) for p in picks)

# 3) Decoupe + sous-titres + export
from faster_whisper import WhisperModel
model = WhisperModel("small", compute_type="int8")


def srt_time(t):
    ms = int((t - int(t)) * 1000)
    return f"{hms(t)},{ms:03d}"


captions = [
    "أول ما جربنا GTA6… ردة الفعل ما تتنسى! 🎮🔥",
    "رسومات GTA6 جنونية! شوفوا بأنفسكم 😱",
    "لحظة مضحكة من البث، ما راح تقدر توقف ضحك 😂",
    "أصعب مهمة في GTA6… هل نجحنا؟ 💥",
    "مطاردة شرطة بجنون! 🚔",
    "لا تفوّت الفرصة! سحب على 3 أجهزة PS5 🎁",
    "مفاجأة ما كنا نتوقعها أثناء اللعب 😳",
    "أجمل لحظات بث GTA6 مع إلياس المالكي ⭐",
    "ردة فعل لا تُصدق! 🔥",
    "تابعونا على Kick لمزيد من البثوث والجوائز 🔔",
]
tags = "#GTA6 #GTA6Gameplay #كيك #ألعاب #جيم_بلاي #PS5 #سحب #giveaway #Kick #ilyaselmaliki"
credit = "🎥 المصدر: بث @ilyaselmaliki على Kick"
lines = []

for k, s in enumerate(starts, 1):
    name = f"clip{k:02d}"
    raw, srt, out = f"{name}_raw.mp4", f"{name}.srt", f"clips/{name}.mp4"
    run(["ffmpeg", "-y", "-ss", str(s), "-t", str(DUR), "-i", "vod.mp4",
         "-c:v", "libx264", "-c:a", "aac", raw])
    segs, _ = model.transcribe(raw, language="ar")
    with open(srt, "w", encoding="utf-8") as f:
        for i, sg in enumerate(segs, 1):
            f.write(f"{i}\n{srt_time(sg.start)} --> {srt_time(sg.end)}\n{sg.text.strip()}\n\n")
    style = "FontName=Noto Sans Arabic,FontSize=12,Bold=1,Outline=2,Alignment=2,MarginV=45"
    fc = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,"
          "crop=1080:1920,boxblur=25:5[bg];[b]scale=1080:-2[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,subtitles={srt}:force_style='{style}'[v]")
    run(["ffmpeg", "-y", "-i", raw, "-filter_complex", fc, "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", out])
    cap = captions[(k - 1) % len(captions)]
    lines.append(f"{name}.mp4  (moment {hms(s)} dans le VOD)\n{cap}\n{credit}\n{tags}\n")

open("clips/captions.txt", "w", encoding="utf-8").write("\n".join(lines))
print("Termine :", len(starts), "clips")
