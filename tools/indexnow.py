"""Signale les URL du sitemap à IndexNow après un déploiement (Bing, Yandex, Seznam, Naver ; Google n'utilise pas IndexNow).

Usage : py -3 tools/indexnow.py [--dry-run]

La clé n'est pas un secret : elle doit être publique, servie à la racine du site dans le fichier public/<clé>.txt,
qui prouve aux moteurs que le domaine autorise ces notifications. Statut 200 ou 202 : notification acceptée.
Code de sortie 1 si la notification échoue.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
PUBLIC = Path(__file__).resolve().parent.parent / "public"
HOST = "uneminutepourcomprendre.fr"
INDEXNOW_KEY = "d0d097f271990270389a1b99c06f425f"
ENDPOINT = "https://api.indexnow.org/indexnow"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="afficher la notification sans l'envoyer")
    args = ap.parse_args()

    key_file = PUBLIC / f"{INDEXNOW_KEY}.txt"
    if not key_file.exists() or key_file.read_text(encoding="utf-8").strip() != INDEXNOW_KEY:
        raise SystemExit(f"Fichier de clé absent ou incorrect : {key_file.relative_to(PUBLIC.parent)}")
    urls = re.findall(r"<loc>(.*?)</loc>", (PUBLIC / "sitemap.xml").read_text(encoding="utf-8"))
    payload = {"host": HOST, "key": INDEXNOW_KEY, "keyLocation": f"https://{HOST}/{INDEXNOW_KEY}.txt", "urlList": urls}
    print(f"{len(urls)} URL, clé servie à {payload['keyLocation']}")
    for u in urls:
        print(f"  {u}")
    if args.dry_run:
        print("Simulation : rien n'est envoyé.")
        return

    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except OSError as e:  # réseau, TLS, délai
        raise SystemExit(f"ÉCHEC : IndexNow injoignable ({e})")
    meaning = {200: "acceptée", 202: "acceptée, clé en cours de validation", 400: "requête invalide",
               403: "clé refusée : le fichier de clé est-il en ligne ?", 422: "URL hors du domaine", 429: "trop de requêtes"}
    print(f"{'OK' if status in (200, 202) else 'ÉCHEC'} : statut {status} ({meaning.get(status, 'inattendu')})")
    sys.exit(0 if status in (200, 202) else 1)


if __name__ == "__main__":
    main()
