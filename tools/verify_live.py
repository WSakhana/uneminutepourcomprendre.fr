"""Vérifie le site en ligne après un déploiement (réseau, lecture seule).

Usage : py -3 tools/verify_live.py [--base https://uneminutepourcomprendre.fr]

Contrôle : statut 200 de chaque URL du sitemap local, redirections (http, www, index.html), page 404
personnalisée, ressources locales des pages (CSS, JS, images), URL canonique des pages, et les en-têtes de sécurité.
Code de sortie 1 si un contrôle échoue.
"""
import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indexnow import INDEXNOW_KEY  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
PUBLIC = Path(__file__).resolve().parent.parent / "public"
UA = {"User-Agent": "Mozilla/5.0 (verify_live.py)"}
failures = []


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch(url, follow=True, method="GET"):
    """Renvoie (statut, en-têtes, corps) sans lever d'exception sur 3xx/4xx/5xx."""
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers=UA, method=method)
    try:
        with opener.open(req, timeout=30) as r:
            return r.status, r.headers, r.read() if method == "GET" else b""
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read() if method == "GET" else b""
    except Exception as e:  # réseau, TLS, délai
        return 0, {}, str(e).encode()


def check(label, ok, detail=""):
    print(f"{'OK  ' if ok else 'FAIL'} {label}{('  ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://uneminutepourcomprendre.fr")
    base = ap.parse_args().base.rstrip("/")
    host = urlparse(base).netloc

    sitemap = (PUBLIC / "sitemap.xml").read_text(encoding="utf-8")
    paths = [urlparse(u).path for u in re.findall(r"<loc>(.*?)</loc>", sitemap)]
    pages = {}
    print("== pages du sitemap")
    for p in paths:
        status, headers, body = fetch(base + p)
        check(f"200 {p}", status == 200, f"(reçu {status})" if status != 200 else "")
        pages[p] = body.decode("utf-8", "replace")
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', pages[p])
        if canonical:
            check(f"canonical {p}", canonical.group(1) == f"https://{host}{p}" or base != f"https://{host}",
                  canonical.group(1))

    print("== redirections")
    status, headers, _ = fetch(f"http://{host}/articles/", follow=False)
    check("http -> https", status in (301, 302) and str(headers.get("Location", "")).startswith("https://"), f"({status})")
    status, headers, _ = fetch(f"https://www.{host}/articles/", follow=False)
    check("www -> sans www", status in (301, 302) and f"//{host}" in str(headers.get("Location", "")), f"({status})")
    article_paths = [p for p in paths if p.startswith("/articles/") and p != "/articles/"]
    for p in article_paths[:1]:
        status, headers, _ = fetch(base + p + "index.html", follow=False)
        check("index.html -> URL propre", status == 301 and str(headers.get("Location", "")).endswith(p), f"({status})")

    print("== fichiers pour les moteurs")
    for name, marker in (("/robots.txt", "Sitemap:"), ("/llms.txt", "# Une Minute Pour Comprendre"), ("/feed.xml", "<rss"),
                         (f"/{INDEXNOW_KEY}.txt", INDEXNOW_KEY)):
        status, _, body = fetch(base + name)
        check(f"200 {name}", status == 200 and marker in body.decode("utf-8", "replace"), f"(reçu {status})" if status != 200 else "")

    print("== page 404")
    status, _, body = fetch(base + "/cette-page-nexiste-pas-umpc")
    check("404 avec la page du site", status == 404 and "Page introuvable" in body.decode("utf-8", "replace"), f"({status})")

    print("== ressources locales des pages")
    assets = set()
    for p, html in pages.items():
        for ref in re.findall(r'(?:href|src)="(/?[^"#]+\.(?:css|js|webp|png|jpg|jpeg|ico|woff2))(?:\?[^"]*)?"', html):
            assets.add(urljoin(base + p, ref))
        for part in re.findall(r'srcset="([^"]+)"', html):
            for item in part.split(","):
                assets.add(urljoin(base + p, item.strip().split()[0]))
    bad = []
    for u in sorted(assets):
        status, _, _ = fetch(u, method="HEAD")
        if status != 200:
            bad.append(f"{status} {u}")
    check(f"{len(assets)} ressources en 200", not bad, "; ".join(bad[:5]))

    print("== en-têtes")
    _, headers, _ = fetch(base + "/")
    for name in ("X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options"):
        check(name, bool(headers.get(name)), str(headers.get(name)))

    print("\nÉCHEC : " + ", ".join(failures) if failures else "\nOK : le site en ligne est conforme")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
