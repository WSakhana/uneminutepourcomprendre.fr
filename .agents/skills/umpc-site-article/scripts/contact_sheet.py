"""Planche contact horodatée d'une vidéo, pour choisir les images d'un article (champ video_time).

Usage :
  py -3 .agents/skills/umpc-site-article/scripts/contact_sheet.py --video <video.mp4> --times 30,153,210 --out planche.png
  py -3 .agents/skills/umpc-site-article/scripts/contact_sheet.py --video <video.mp4> --start 140 --end 170 --step 3 --out planche.png

Chaque vignette porte son instant en secondes (c'est la valeur à mettre dans video_time). Écrire la planche hors du dépôt
(dossier temporaire), puis l'ouvrir pour la regarder : les images à mi-animation sont souvent vides, il faut comparer
plusieurs instants d'une même scène avant de choisir. Nécessite ffmpeg et Pillow.
"""
import argparse
import io
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8")


def frame(video, t, width):
    out = subprocess.run(
        [shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
         "-vf", f"scale={width}:-1", "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True)
    if out.returncode or not out.stdout:
        return None
    return Image.open(io.BytesIO(out.stdout)).convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--times", help="instants en secondes, séparés par des virgules")
    ap.add_argument("--start", type=float)
    ap.add_argument("--end", type=float)
    ap.add_argument("--step", type=float, default=3.0)
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--width", type=int, default=480, help="largeur d'une vignette")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    if a.times:
        times = [float(x) for x in a.times.split(",") if x.strip()]
    elif a.start is not None and a.end is not None:
        times, t = [], a.start
        while t <= a.end + 1e-6:
            times.append(round(t, 2))
            t += a.step
    else:
        raise SystemExit("Donner --times, ou --start et --end.")
    if len(times) > 24:
        raise SystemExit(f"{len(times)} vignettes : trop pour une seule planche lisible (24 maximum), augmenter --step.")

    thumbs = [(t, frame(a.video, t, a.width)) for t in times]
    thumbs = [(t, im) for t, im in thumbs if im is not None]
    if not thumbs:
        raise SystemExit("Aucune image extraite : vérifier le chemin de la vidéo et les instants.")
    w, h = thumbs[0][1].size
    rows = (len(thumbs) + a.cols - 1) // a.cols
    sheet = Image.new("RGB", (w * a.cols, h * rows), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    for i, (t, im) in enumerate(thumbs):
        x, y = (i % a.cols) * w, (i // a.cols) * h
        sheet.paste(im, (x, y))
        d.rectangle((x, y, x + 78, y + 20), fill=(0, 0, 0))
        d.text((x + 5, y + 4), f"{t:g} s", fill=(255, 212, 0))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(a.out)
    print(f"{a.out} : {len(thumbs)} vignettes ({sheet.width}x{sheet.height})")


if __name__ == "__main__":
    main()
