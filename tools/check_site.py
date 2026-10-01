"""Contrôle statique de public/ avant mise en ligne (aucun réseau).

Usage : py -3 tools/check_site.py
Vérifie, pour chaque page : identifiants uniques, un seul h1, titre non vide, alt et dimensions des images,
rel="noopener" sur les liens target=_blank, cibles locales et ancres existantes, meta description <= 160 caractères,
et que chaque URL du sitemap correspond à une page. Contrôles SEO : URL canonique égale à l'URL de la page, balises
Open Graph et image de partage, données structurées (JSON-LD) valides, titres et descriptions uniques, pages noindex
absentes du sitemap, robots.txt, llms.txt et flux RSS. Code de sortie 1 s'il y a un problème.
"""
import html as htmllib
import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8")
PUBLIC = Path(__file__).resolve().parent.parent / "public"
SITE = "https://uneminutepourcomprendre.fr"
problems = []


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.refs, self.links, self.assets, self.imgs = [], [], [], [], []
        self.h1 = 0
        self.title = ""
        self._in_title = False
        self.blank_no_rel = []

    def handle_starttag(self, tag, a):
        a = dict(a)
        if "id" in a:
            self.ids.append(a["id"])
        for k in ("aria-labelledby",):
            if k in a:
                self.refs.append(a[k])
        if tag == "h1":
            self.h1 += 1
        if tag == "title":
            self._in_title = True
        if tag == "a" and "href" in a:
            self.links.append(a["href"])
            if a.get("target") == "_blank" and "noopener" not in a.get("rel", ""):
                self.blank_no_rel.append(a["href"])
        if tag in ("img", "script", "link", "source") and (a.get("src") or a.get("href")):
            self.assets.append(a.get("src") or a.get("href"))
            for part in (a.get("srcset") or "").split(","):
                if part.strip():
                    self.assets.append(part.strip().split()[0])
        if tag == "img":
            self.imgs.append(a)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, d):
        if self._in_title:
            self.title += d


def local_target(base, ref):
    u = urlparse(ref)
    if u.scheme or u.netloc or ref.startswith(("mailto:", "tel:", "data:")):
        return None
    path = u.path
    if not path:
        return base
    p = (PUBLIC / path.lstrip("/")) if path.startswith("/") else (base.parent / path)
    if p.is_dir() or path.endswith("/"):
        p = p / "index.html"
    return p


def page_url(f):
    """URL publique d'une page de public/ : index.html devient l'URL propre de son dossier."""
    rel = f.relative_to(PUBLIC).as_posix()
    return f"{SITE}/" + ("" if rel == "index.html" else rel[: -len("index.html")] if rel.endswith("/index.html") else rel)


seen_titles, seen_descs, noindex_urls = {}, {}, set()


def seen(store, value, rel, label):
    if value in store:
        problems.append(f"{rel}: {label} identique à celui de {store[value]}")
    store[value] = rel


def seo_check(f, rel, text, p):
    robots = re.search(r'<meta name="robots" content="([^"]*)"', text)
    if robots and "noindex" in robots.group(1):
        noindex_urls.add(page_url(f))
    else:
        canon = re.search(r'<link rel="canonical" href="([^"]+)"', text)
        if not canon:
            problems.append(f"{rel}: canonical absent")
        elif canon.group(1) != page_url(f):
            problems.append(f"{rel}: canonical {canon.group(1)} différent de l'URL attendue {page_url(f)}")
    og = dict(re.findall(r'<meta property="(og:[a-z:_]+)" content="([^"]*)"', text))
    for k in ("og:title", "og:description", "og:url", "og:image", "og:image:alt"):
        if not og.get(k):
            problems.append(f"{rel}: balise {k} absente")
    img = og.get("og:image", "")
    if img.startswith(SITE) and not (PUBLIC / img[len(SITE):].lstrip("/")).exists():
        problems.append(f"{rel}: image de partage absente {img}")
    for k in ("twitter:card", "twitter:image"):
        if f'name="{k}"' not in text:
            problems.append(f"{rel}: balise {k} absente")
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)
    if not blocks and page_url(f) not in noindex_urls:
        problems.append(f"{rel}: aucune donnée structurée JSON-LD")
    for b in blocks:
        try:
            data = json.loads(b)
        except ValueError as e:
            problems.append(f"{rel}: JSON-LD invalide ({e})")
            continue
        nodes = data.get("@graph", [data])
        ids = {n["@id"] for n in nodes if "@id" in n}
        for n in nodes:
            for v in n.values():
                ref = v.get("@id") if isinstance(v, dict) and set(v) == {"@id"} else None
                if ref and ref not in ids and not ref.startswith(SITE + "/#"):
                    problems.append(f"{rel}: JSON-LD, référence @id sans nœud {ref}")
    seen(seen_titles, p.title.strip(), rel, "titre")
    desc = re.search(r'<meta name="description" content="([^"]*)"', text)
    if desc:
        seen(seen_descs, desc.group(1), rel, "description")


pages = sorted(PUBLIC.rglob("*.html"))
parsed = {}
for f in pages:
    text = f.read_text(encoding="utf-8")
    p = P()
    p.feed(text)
    parsed[f] = p
for f, p in parsed.items():
    rel = f.relative_to(PUBLIC)
    dup = {i for i in p.ids if p.ids.count(i) > 1}
    if dup:
        problems.append(f"{rel}: id dupliqués {dup}")
    for r in p.refs:
        if r not in p.ids:
            problems.append(f"{rel}: aria-labelledby vers id absent {r}")
    if p.h1 != 1 and f.name != "404.html":
        problems.append(f"{rel}: {p.h1} balises h1")
    if f.name == "404.html" and p.h1 != 1:
        problems.append(f"{rel}: {p.h1} balises h1")
    if not p.title or len(p.title) > 70:  # au-delà, Google tronque le titre dans les résultats
        problems.append(f"{rel}: titre vide ou trop long ({len(p.title)})")
    for img in p.imgs:
        if "alt" not in img:
            problems.append(f"{rel}: img sans alt {img.get('src')}")
        if "width" not in img or "height" not in img:
            problems.append(f"{rel}: img sans dimensions {img.get('src')}")
    for href in p.blank_no_rel:
        problems.append(f"{rel}: target=_blank sans noopener {href}")
    for ref in p.links + p.assets:
        t = local_target(f, ref)
        if t is None:
            continue
        if not t.exists():
            problems.append(f"{rel}: cible locale absente {ref}")
            continue
        frag = urlparse(ref).fragment
        if frag and t in parsed and frag not in parsed[t].ids:
            problems.append(f"{rel}: ancre absente {ref}")
    text = f.read_text(encoding="utf-8")
    meta = re.search(r'<meta name="description" content="([^"]*)"', text)
    if meta:
        n = len(htmllib.unescape(meta.group(1)))
        if n > 160:
            problems.append(f"{rel}: meta description {n} caractères (> 160)")
        print(f"{rel}: description {n} caractères, titre {len(p.title)} caractères")
    else:
        problems.append(f"{rel}: meta description absente")
    seo_check(f, rel, text, p)

# sitemap : toutes les URL existent et sont absentes du sitemap si noindex
sm = (PUBLIC / "sitemap.xml").read_text(encoding="utf-8")
for loc in re.findall(r"<loc>(.*?)</loc>", sm):
    path = urlparse(loc).path
    tgt = PUBLIC / path.lstrip("/")
    if path.endswith("/"):
        tgt = tgt / "index.html"
    if not tgt.exists():
        problems.append(f"sitemap: URL sans page {loc}")

for loc in re.findall(r"<loc>(.*?)</loc>", sm):
    if loc in noindex_urls:
        problems.append(f"sitemap: page noindex {loc}")
for loc, last in re.findall(r"<loc>(.*?)</loc>\s*<lastmod>(.*?)</lastmod>", sm):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", last):
        problems.append(f"sitemap: lastmod invalide pour {loc} ({last})")

# fichiers à la racine : robots.txt, llms.txt, flux RSS
robots_file = PUBLIC / "robots.txt"
robots = robots_file.read_text(encoding="utf-8") if robots_file.exists() else ""
if f"Sitemap: {SITE}/sitemap.xml" not in robots:
    problems.append("robots.txt: ligne Sitemap absente")
if re.search(r"^Disallow:\s*/\s*$", robots, re.M):
    problems.append("robots.txt: Disallow: / bloque tout le site")
llms = PUBLIC / "llms.txt"
if not llms.exists():
    problems.append("llms.txt absent (py -3 tools/build_articles.py)")
else:
    for loc in re.findall(r"\]\((" + re.escape(SITE) + r"[^)]*)\)", llms.read_text(encoding="utf-8")):
        path = urlparse(loc).path
        tgt = PUBLIC / path.lstrip("/")
        if (path.endswith("/") and not (tgt / "index.html").exists()) or (not path.endswith("/") and not tgt.exists()):
            problems.append(f"llms.txt: lien sans page {loc}")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from indexnow import INDEXNOW_KEY  # noqa: E402

key_file = PUBLIC / f"{INDEXNOW_KEY}.txt"
if not key_file.exists() or key_file.read_text(encoding="utf-8").strip() != INDEXNOW_KEY:
    problems.append(f"fichier de clé IndexNow absent ou incorrect : {key_file.name}")
try:
    n_items = len(ET.parse(PUBLIC / "feed.xml").getroot().findall("./channel/item"))
    n_articles = len([loc for loc in re.findall(r"<loc>(.*?)</loc>", sm) if "/articles/" in loc and not loc.endswith("/articles/")])
    if n_items != n_articles:
        problems.append(f"feed.xml: {n_items} articles pour {n_articles} dans le sitemap")
except (OSError, ET.ParseError) as e:
    problems.append(f"feed.xml absent ou invalide ({e})")

print("\n".join(problems) if problems else "OK : aucun problème")
sys.exit(1 if problems else 0)
