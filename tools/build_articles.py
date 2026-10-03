"""Génère les pages « Articles » du site à partir de content/articles/.

Outil de développement local : il n'est pas à envoyer sur l'hébergement.
Usage : py -3 tools/build_articles.py [--images]   (nécessite Pillow ; ffmpeg pour les images extraites d'une vidéo)

Pour chaque dossier content/articles/<slug>/ (article.toml + body.html), le script écrit :
  public/articles/index.html                      liste des articles
  public/articles/<slug>/index.html               page de l'article
  public/404.html                                 page d'erreur
  public/assets/img/articles/<slug>/*.webp, og.jpg  images
et met à jour le bloc « Derniers articles » de public/index.html (entre les marqueurs
<!-- articles:start --> et <!-- articles:end -->) ainsi que public/sitemap.xml (avec les images),
public/feed.xml (flux RSS) et public/llms.txt (présentation du site pour les moteurs de réponse IA).
Les images ne sont régénérées que si elles manquent, ou avec --images.
"""
import argparse
import hashlib
import html
import io
import json
import re
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_assets import crop_to  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
CONTENT = ROOT / "content" / "articles"
SITE = "https://uneminutepourcomprendre.fr"
ORG_ID = f"{SITE}/#organization"
CHANNEL = "https://www.youtube.com/@1min.pour.comprendre"
WIDTHS = (640, 1280)
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
COPY_ICON = ('<svg class="icon icon-copy" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
             '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/></svg>'
             '<svg class="icon icon-check" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
             '<path d="m5 12.5 4.5 4.5L19 7.5"/></svg>')
LINK_ICON = ('<svg class="icon icon-copy" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
             '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>'
             '<svg class="icon icon-check" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
             '<path d="m5 12.5 4.5 4.5L19 7.5"/></svg>')
HOME_OG_ALT = "Logo et nom Une Minute Pour Comprendre à côté d'illustrations scientifiques de la chaîne."
FEED_TITLE = "Une Minute Pour Comprendre : articles"
SITE_DESC = ("Vulgarisation scientifique en vidéo : des phénomènes étonnants de la science, des animaux, du corps humain "
             "et de la nature expliqués simplement et en images.")
DEFAULT_METHOD = "Cet article reprend et développe la vidéo. Les affirmations sont limitées à ce que les sources citées établissent."

SOCIALS = [
    ("youtube", "YouTube", CHANNEL),
    ("tiktok", "TikTok", "https://www.tiktok.com/@1min.pour.comprendre"),
    ("instagram", "Instagram", "https://www.instagram.com/1min.pour.comprendre/"),
    ("facebook", "Facebook", "https://www.facebook.com/1min.pour.comprendre"),
]


def asset(path):
    """URL d'un fichier de public/ avec une empreinte (?v=...) : le cache d'un mois se renouvelle à chaque modification."""
    # Fins de ligne normalisées : même empreinte sous Windows (CRLF possible) et sur la CI Linux (LF).
    digest = hashlib.md5((PUBLIC / path.lstrip("/")).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:8]
    return f"{path}?v={digest}"


def esc(s):
    return html.escape(str(s), quote=True)


def fr_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{'1er' if d == 1 else d} {MONTHS[m - 1]} {y}"


def fmt_time(seconds):
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def fmt_duration(seconds):
    s = int(seconds)
    return f"{s // 60} min {s % 60:02d}"


def iso_duration(seconds):
    s = int(seconds)
    return f"PT{s // 60}M{s % 60}S"


def json_ld(data):
    return json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")


# ----------------------------------------------------------------------------- images


def extract_video_frame(video, seconds):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg introuvable : nécessaire pour extraire les images de la vidéo.")
    out = subprocess.run(
        [ffmpeg, "-v", "error", "-ss", str(seconds), "-i", str(video), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        check=True, capture_output=True,
    ).stdout
    return Image.open(io.BytesIO(out))


def build_images(art, force):
    """Écrit les WebP de chaque image ; renvoie {clé: [(largeur nominale, largeur, hauteur), ...]}."""
    out_dir = PUBLIC / "assets" / "img" / "articles" / art["slug"]
    out_dir.mkdir(parents=True, exist_ok=True)
    prod = Path(art["production"])
    sizes = {}
    for key, cfg in art["images"].items():
        targets = {w: out_dir / f"{key}-{w}.webp" for w in WIDTHS}
        small, big = targets[WIDTHS[0]], targets[WIDTHS[-1]]
        # Une source plus étroite que 640 px n'a qu'une version : elle est complète sans la 1280 (et le build n'a alors
        # pas besoin du dossier de production, absent de la CI).
        complete = small.exists() and (big.exists() or Image.open(small).width < WIDTHS[0])
        if force or not complete:
            if "video_time" in cfg:
                im = extract_video_frame(prod / art["video_file"], cfg["video_time"])
            else:
                im = Image.open(prod / cfg["src"])
            im = im.convert("RGB")
            if "box" in cfg:
                x0, y0, x1, y1 = cfg["box"]
                im = im.crop((round(x0 * im.width), round(y0 * im.height), round(x1 * im.width), round(y1 * im.height)))
            for w, path in targets.items():
                if w != WIDTHS[0] and im.width <= WIDTHS[0]:
                    path.unlink(missing_ok=True)  # pas d'agrandissement : une seule version pour une petite source
                    continue
                width = min(w, im.width)
                im.resize((width, round(width * im.height / im.width)), Image.LANCZOS).save(path, "WEBP", quality=78, method=6)
            if key == art["cover"]:
                crop_to(im, 1200 / 630, 0.5, 0.5).resize((1200, 630), Image.LANCZOS).save(
                    out_dir / "og.jpg", "JPEG", quality=84, optimize=True, progressive=True)
        sizes[key] = [(w, *Image.open(p).size) for w, p in targets.items() if p.exists()]
    return sizes


def img_url(slug, key, w):
    return f"/assets/img/articles/{slug}/{key}-{w}.webp"


def img_tag(art, key, sizes, sizes_attr, loading="lazy"):
    cfg, avail = art["images"][key], sizes[key]
    srcset = ", ".join(f"{img_url(art['slug'], key, nominal)} {w}w" for nominal, w, _ in avail)
    nominal, w, h = avail[-1]
    return (f'<img src="{img_url(art["slug"], key, nominal)}" srcset="{srcset}" sizes="{sizes_attr}" width="{w}" height="{h}" '
            f'alt="{esc(cfg["alt"])}" loading="{loading}" decoding="async">')


# ----------------------------------------------------------------------------- gabarits communs


def sprite():
    m = re.search(r'<svg class="sprite".*?</svg>', (PUBLIC / "index.html").read_text(encoding="utf-8"), re.S)
    return m.group(0)


def head(title, description, path, og_type, og_image, ld=None, extra_meta="", robots="index, follow, max-image-preview:large", og_alt=HOME_OG_ALT):
    url = f"{SITE}{path}"
    ld_block = f'  <script type="application/ld+json">\n{json_ld(ld)}\n  </script>\n' if ld else ""
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <link rel="canonical" href="{url}">
  <meta name="robots" content="{robots}">
  <meta name="theme-color" content="#0A1633">
  <meta name="color-scheme" content="dark">

  <meta property="og:type" content="{og_type}">
  <meta property="og:site_name" content="Une Minute Pour Comprendre">
  <meta property="og:locale" content="fr_FR">
  <meta property="og:url" content="{url}">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:image" content="{SITE}{og_image}">
  <meta property="og:image:type" content="image/jpeg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{esc(og_alt)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{esc(title)}">
  <meta name="twitter:description" content="{esc(description)}">
  <meta name="twitter:image" content="{SITE}{og_image}">
  <meta name="twitter:image:alt" content="{esc(og_alt)}">
{extra_meta}
  <link rel="icon" href="/favicon.ico" sizes="48x48">
  <link rel="icon" href="/favicon-32.png" type="image/png" sizes="64x64">
  <link rel="icon" href="/icon-192.png" type="image/png" sizes="192x192">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="alternate" type="application/rss+xml" title="{esc(FEED_TITLE)}" href="/feed.xml">

  <link rel="preload" href="/assets/fonts/archivo-variable.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="stylesheet" href="{asset("/assets/css/style.css")}">

{ld_block}</head>
"""


def header():
    return """  <a class="skip-link" href="#contenu">Aller au contenu</a>

  <header class="site-header">
    <div class="container header-inner">
      <a class="brand" href="/" aria-label="Une Minute Pour Comprendre, retour à l'accueil">
        <img src="/assets/img/logo-96.webp" srcset="/assets/img/logo-96.webp 1x, /assets/img/logo-192.webp 2x" width="44" height="44" alt="">
        <span class="brand-name">Une Minute <span>Pour Comprendre</span></span>
      </a>
      <nav class="header-nav" aria-label="Navigation principale">
        <ul>
          <li><a href="/#concept">Le concept</a></li>
          <li><a href="/#univers">Univers</a></li>
          <li class="nav-always"><a href="/articles/" {current}>Articles</a></li>
        </ul>
        <a class="btn btn-small" href="/#reseaux">Suivre</a>
      </nav>
    </div>
  </header>
"""


def footer(extra_script=""):
    links = "\n".join(
        f'        <li><a href="{u}" target="_blank" rel="me noopener" aria-label="{n} (nouvel onglet)"><svg class="icon" aria-hidden="true" focusable="false"><use href="#i-{k}"/></svg></a></li>'
        for k, n, u in SOCIALS)
    return f"""  <footer class="site-footer">
    <div class="container footer-inner">
      <div class="footer-brand">
        <img src="/assets/img/logo-96.webp" width="40" height="40" alt="" loading="lazy" decoding="async">
        <div>
          <p class="footer-name">Une Minute Pour Comprendre</p>
          <p class="handle">@1min.pour.comprendre</p>
        </div>
      </div>
      <ul class="footer-social" aria-label="Réseaux sociaux">
{links}
      </ul>
      <p class="copyright">© <span id="year">2026</span> Une Minute Pour Comprendre <span class="made-by">· Un projet <a href="https://zoneia.fr" target="_blank" rel="noopener">Zone IA</a></span></p>
    </div>
  </footer>
  <script>document.getElementById("year").textContent = new Date().getFullYear();</script>{extra_script}
</body>
</html>
"""


def page(head_html, main_html, current_articles=True, scripts=()):
    hdr = header().replace(" {current}", ' aria-current="page"' if current_articles else "")
    tags = "".join(f'\n  <script src="{asset(s)}" defer></script>' for s in ("/assets/js/site.js", *scripts))
    return f'{head_html}<body>\n  {sprite()}\n\n{hdr}\n  <main id="contenu">\n{main_html}\n  </main>\n\n{footer(tags)}'


# ----------------------------------------------------------------------------- contenu


REQUIRED = ("slug", "title", "short_title", "category", "description", "lead", "published", "modified", "cover",
            "production", "video", "chapters", "sources")


def find_todos(value, path=""):
    """Chemins des valeurs qui contiennent encore un « TODO » (brouillon de inspect_production.py)."""
    if isinstance(value, str):
        return [path] if "TODO" in value else []
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in find_todos(v, f"{path}.{k}" if path else k)]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in find_todos(v, f"{path}[{i}]")]
    return []


def load_articles():
    arts = []
    for d in sorted(p for p in CONTENT.glob("*/") if p.is_dir()):
        name = d.name
        toml_path, body_path = d / "article.toml", d / "body.html"
        if not toml_path.exists() or not body_path.exists():
            raise SystemExit(f"{name} : article.toml et body.html sont tous deux nécessaires.")
        meta = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        meta["body"] = body_path.read_text(encoding="utf-8")
        missing = [k for k in REQUIRED if k not in meta]
        if missing:
            raise SystemExit(f"{name} : champs manquants dans article.toml : {', '.join(missing)}")
        if meta["slug"] != name:
            raise SystemExit(f"{name} : le slug ({meta['slug']}) doit être identique au nom du dossier.")
        todos = find_todos(meta) + (["body.html"] if "TODO" in meta["body"] else [])
        if todos:
            raise SystemExit(f"{name} : il reste des TODO à remplir : {', '.join(todos[:12])}")
        if len(meta["description"]) > 160:
            raise SystemExit(f"{name} : description de {len(meta['description'])} caractères, 160 au maximum (meta description).")
        if meta["cover"] not in meta.get("images", {}):
            raise SystemExit(f"{name} : cover = {meta['cover']!r} n'est pas une clé de [images.*]")
        meta["images"] = meta.get("images", {})
        arts.append(meta)
    arts.sort(key=lambda a: a["published"], reverse=True)
    return arts


def word_count(body):
    """Nombre de mots du texte de l'article (balises et marqueurs {{...}} exclus)."""
    return len(re.sub(r"<[^>]+>|\{\{[^}]*\}\}", " ", body).split())


def reading_minutes(body):
    return max(1, round(word_count(body) / 220))


def render_body(art, sizes):
    body, slug = art["body"], art["slug"]
    sources = {s["id"]: i + 1 for i, s in enumerate(art["sources"])}
    chapters = {c["t"]: c for c in art["chapters"]}
    vid = art["video"]["id"]
    used_images, cited = [], []

    def figure(m):
        key = m.group(1)
        if key not in art["images"]:
            raise SystemExit(f"Image inconnue dans body.html : {key}")
        used_images.append(key)
        cfg, avail = art["images"][key], sizes[key]
        narrow = " article-figure--narrow" if avail[-1][1] < avail[-1][2] else ""
        credit = esc(cfg["credit"])
        if cfg.get("credit_url"):
            credit = f'<a href="{esc(cfg["credit_url"])}" target="_blank" rel="noopener noreferrer">{credit}<span class="sr-only"> (nouvel onglet)</span></a>'
        badge = '<span class="fig-badge">Illustration</span> ' if cfg.get("generated") else ""
        return (f'<figure class="article-figure{narrow}">{img_tag(art, key, sizes, "(min-width: 960px) 760px, 100vw")}'
                f'<figcaption>{badge}{esc(cfg["caption"])} <span class="fig-credit">{credit}</span></figcaption></figure>')

    def cite(m):
        sid = m.group(1)
        if sid not in sources:
            raise SystemExit(f"Source inconnue dans body.html : {sid}")
        cited.append(sid)
        n = sources[sid]
        return f'<sup class="cite"><a href="#source-{n}" aria-label="Source {n}">[{n}]</a></sup>'

    def chapter(m):
        t = int(m.group(1))
        if t not in chapters:
            raise SystemExit(f"Chapitre inconnu dans body.html : {t}")
        c = chapters[t]
        return (f'<a class="btn btn-ghost btn-small" href="https://youtu.be/{vid}?t={t}" target="_blank" rel="noopener noreferrer">'
                f'<svg class="icon" aria-hidden="true" focusable="false"><use href="#i-youtube"/></svg>'
                f'Voir ce passage dans la vidéo ({fmt_time(t)})<span class="sr-only"> : {esc(c["label"])} (nouvel onglet)</span></a>')

    body = re.sub(r"\{\{figure:(\w+)\}\}", figure, body)
    body = re.sub(r"\{\{cite:(S\d+)\}\}", cite, body)
    body = re.sub(r"\{\{chapitre:(\d+)\}\}", chapter, body)
    unused = [s["id"] for s in art["sources"] if s["id"] not in cited]
    if unused:
        raise SystemExit(f"Sources listées mais jamais citées dans le texte : {', '.join(unused)}")
    return body, used_images


def anchor_button(anchor, label):
    """Bouton « copier le lien de cette section » (caché tant que le JavaScript n'est pas actif)."""
    return (f'<button type="button" class="copy-btn copy-btn--anchor" data-copy-anchor="{anchor}" '
            f'title="Copier le lien de cette section" aria-label="Copier le lien de la section : {esc(label)}" hidden>{LINK_ICON}</button>')


def add_anchor_buttons(body):
    """Ajoute le bouton à la fin du titre de chaque <section id=...> du corps."""
    def one(m):
        label = re.sub(r"<[^>]+>", "", re.sub(r'<span class="cas-num"[^>]*>\d</span>', "", m.group(3))).strip()
        return f"{m.group(1)}{m.group(3)}{anchor_button(m.group(2), label)}</h2>"
    return re.sub(r'(<section id="([\w-]+)">\s*<h2[^>]*>)(.*?)</h2>', one, body, flags=re.S)


def toc_entries(body):
    out = []
    for m in re.finditer(r'<section id="([\w-]+)">\s*<h2[^>]*>(.*?)</h2>', body, re.S):
        text = re.sub(r'<span class="cas-num"[^>]*>(\d)</span>', r"\1. ", m.group(2))
        out.append((m.group(1), re.sub(r"<[^>]+>", "", text)))
    return out


def sources_html(art):
    items = []
    for i, s in enumerate(art["sources"], 1):
        # Une source sans page publique (musique de la vidéo, par exemple) n'a ni lien ni bouton de copie.
        link = (f' <a class="src-link" href="{esc(s["url"])}" target="_blank" rel="noopener noreferrer">Consulter la publication<span class="sr-only"> (nouvel onglet)</span></a>\n'
                f'            <button type="button" class="copy-btn" data-copy="{esc(s["url"])}" title="Copier le lien de la source" aria-label="Copier le lien de la source {i}" hidden>{COPY_ICON}</button>'
                if s.get("url") else "")
        items.append(f"""        <li id="source-{i}">
          <p class="src-ref"><span class="src-authors">{esc(s["authors"])}</span>{f' ({esc(s["year"])})' if s.get("year") else ""}. <cite>{esc(s["title"])}</cite>. <span class="src-pub">{esc(s["publication"])}</span>.</p>
          <p class="src-topic"><strong>Sujet concerné :</strong> {esc(s["topic"])}</p>
          <p class="src-meta"><span class="src-kind">{esc(s["kind"])}</span>{link}</p>
        </li>""")
    return "\n".join(items)


def credits_html(art, used_images):
    items = []
    for key in dict.fromkeys(used_images):
        cfg = art["images"][key]
        if cfg.get("credit_url"):
            items.append(f'        <li>{esc(cfg["caption"])} <span class="fig-credit">{esc(cfg["credit"])} · '
                         f'<a href="{esc(cfg["credit_url"])}" target="_blank" rel="noopener noreferrer">Fichier source<span class="sr-only"> (nouvel onglet)</span></a></span></li>')
    return "\n".join(items)


def article_page(art, sizes, others=()):
    """Écrit la page d'un article ; renvoie les clés des images utilisées dans le texte (pour le sitemap).

    others : [(article, tailles d'images)] des autres articles, pour le bloc « À lire aussi ».
    """
    slug, vid = art["slug"], art["video"]["id"]
    path = f"/articles/{slug}/"
    url = f"{SITE}{path}"
    body, used = render_body(art, sizes)
    minutes = reading_minutes(art["body"])
    dur = art["video"]["duration_seconds"]
    og = f"/assets/img/articles/{slug}/og.jpg"
    keywords = art.get("keywords", [])

    ends = [c["t"] for c in art["chapters"][1:]] + [int(dur)]
    clips = [{"@type": "Clip", "name": c["label"], "startOffset": c["t"], "endOffset": e, "url": f"https://youtu.be/{vid}?t={c['t']}"}
             for c, e in zip(art["chapters"], ends)]
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Accueil", "item": f"{SITE}/"},
                {"@type": "ListItem", "position": 2, "name": "Articles", "item": f"{SITE}/articles/"},
                {"@type": "ListItem", "position": 3, "name": art["short_title"], "item": url}]},
            {"@type": "Article", "@id": f"{url}#article", "headline": art["title"], "description": art["description"],
             "image": [{"@type": "ImageObject", "url": f"{SITE}{og}", "width": 1200, "height": 630}],
             "datePublished": art["published"], "dateModified": art["modified"], "inLanguage": "fr-FR",
             "author": {"@id": ORG_ID}, "publisher": {"@id": ORG_ID}, "mainEntityOfPage": {"@type": "WebPage", "@id": url},
             "isPartOf": {"@id": f"{SITE}/#website"}, "isAccessibleForFree": True,
             "wordCount": word_count(art["body"]), "timeRequired": f"PT{minutes}M",
             **({"keywords": ", ".join(keywords)} if keywords else {}),
             "articleSection": art["category"], "video": {"@id": f"{url}#video"},
             "citation": [{"@type": "CreativeWork", "name": s["title"],
                           **({"datePublished": s["year"]} if s.get("year") else {}),
                           **({"url": s["url"]} if s.get("url") else {}),
                           "isPartOf": {"@type": "Periodical", "name": s["publication"].split(",")[0]}} for s in art["sources"]]},
            {"@type": "VideoObject", "@id": f"{url}#video", "name": art["video"]["title"], "description": art["description"],
             "thumbnailUrl": [f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg", f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"],
             "uploadDate": art["video"]["upload_date"], "duration": iso_duration(dur), "inLanguage": "fr-FR",
             "embedUrl": f"https://www.youtube.com/embed/{vid}", "contentUrl": f"https://www.youtube.com/watch?v={vid}",
             "publisher": {"@id": ORG_ID}, **({"hasPart": clips} if clips else {})},
        ],
    }
    # Titre de la page : suffixe de marque seulement s'il tient sous 70 caractères (sinon Google tronque le titre).
    title = f"{art['title']} | Une Minute Pour Comprendre"
    if len(title) > 70:
        title = art["title"]
    extra = (f'  <meta property="article:published_time" content="{art["published"]}">\n'
             f'  <meta property="article:modified_time" content="{art["modified"]}">\n'
             f'  <meta property="article:section" content="{esc(art["category"])}">'
             + "".join(f'\n  <meta property="article:tag" content="{esc(k)}">' for k in keywords))
    head_html = head(title, art["description"], path, "article", og, ld, extra, og_alt=art["images"][art["cover"]]["alt"])

    chapters_li = "\n".join(
        f'            <li><a href="https://youtu.be/{vid}?t={c["t"]}" target="_blank" rel="noopener noreferrer"><span class="chap-time">{fmt_time(c["t"])}</span> {esc(c["label"])}<span class="sr-only"> (nouvel onglet)</span></a></li>'
        for c in art["chapters"])
    # Un Short n'a pas de chapitres : pas de bloc vide.
    chapters_block = f"""          <details class="chapters">
            <summary>Chapitres de la vidéo</summary>
            <ol>
{chapters_li}
            </ol>
          </details>""" if art["chapters"] else ""
    # Vidéo verticale (Short) : lecteur 9:16.
    frame_class = "video-frame video-frame--vertical" if art["video"].get("vertical") else "video-frame"
    body = add_anchor_buttons(body)
    toc_li = "\n".join(f'          <li><a href="#{i}">{esc(t)}</a></li>' for i, t in toc_entries(body))
    credits = credits_html(art, used)
    updated = (f' (mis à jour le <time datetime="{art["modified"]}">{fr_date(art["modified"])}</time>)'
               if art["modified"] != art["published"] else "")
    related = ""
    if others:
        related_cards = "\n".join(card(a, s, 3) for a, s in others[:3])
        related = f"""
      <section class="article-related" aria-labelledby="related-title">
        <h2 id="related-title" class="related-title">À lire aussi</h2>
        <ul class="article-grid">
{related_cards}
        </ul>
      </section>
"""

    main = f"""    <div class="container article-wrap">
      <nav class="breadcrumb" aria-label="Fil d'Ariane">
        <ol>
          <li><a href="/">Accueil</a></li>
          <li><a href="/articles/">Articles</a></li>
          <li aria-current="page">{esc(art["short_title"])}</li>
        </ol>
      </nav>

      <article class="article">
        <div class="video-block">
          <div class="{frame_class}">
            <iframe src="https://www.youtube-nocookie.com/embed/{vid}?rel=0" title="Vidéo : {esc(art["video"]["title"])}" allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
          </div>
          <div class="video-meta">
            <a class="btn btn-primary" href="https://youtu.be/{vid}" target="_blank" rel="noopener noreferrer"><svg class="icon" aria-hidden="true" focusable="false"><use href="#i-youtube"/></svg>Regarder sur YouTube<span class="sr-only"> (nouvel onglet)</span></a>
            <p class="video-note">Vidéo de la chaîne <a href="{CHANNEL}" target="_blank" rel="me noopener">@1min.pour.comprendre</a> · {fmt_duration(dur)}</p>
          </div>
{chapters_block}
        </div>

        <header class="article-header">
          <p class="kicker">{esc(art["category"])} · Article</p>
          <h1 class="article-title">{esc(art["title"])}</h1>
          <p class="article-lead">{esc(art["lead"])}</p>
          <p class="article-meta"><time datetime="{art["published"]}">{fr_date(art["published"])}</time>{updated} · {minutes} min de lecture · <a href="#sources">{len(art["sources"])} sources</a></p>
        </header>

        <nav class="toc" aria-labelledby="toc-title">
          <h2 id="toc-title" class="toc-title">Dans cet article</h2>
          <ol>
{toc_li}
            <li><a href="#sources">Sources</a></li>
          </ol>
        </nav>

        <div class="prose">
{body}
        </div>

        <section id="sources" class="sources" aria-labelledby="sources-title">
          <h2 id="sources-title" class="sources-title">Sources{anchor_button("sources", "Sources")}</h2>
          <p class="sources-intro">Références utilisées pour préparer la vidéo. Quand plusieurs documents traitent d'un même point, la publication scientifique originale est citée en priorité ; une présentation institutionnelle n'est ajoutée que pour ce que la publication ne donne pas.</p>
          <ol class="source-list">
{sources_html(art)}
          </ol>
          <p id="copy-status" class="sr-only" role="status" aria-live="polite"></p>
        </section>

        <section class="credits" aria-labelledby="credits-title">
          <h2 id="credits-title" class="credits-title">Crédits des images</h2>
          <ul>
{credits}
          </ul>
          <p>Les images marquées « Illustration » ont été générées ou créées pour la vidéo : elles ne représentent pas des observations scientifiques directes. Les schémas repris de la vidéo portent les mêmes mentions.</p>
        </section>

        <aside class="method">
          <h2 class="method-title">À propos de cet article</h2>
          <p>{esc(art.get("method", DEFAULT_METHOD))}</p>
        </aside>
      </article>
{related}
      <section class="cta-panel article-cta" aria-labelledby="article-cta-title">
        <h2 id="article-cta-title" class="section-title">Une question par vidéo. <span class="accent">Une réponse claire.</span></h2>
        <p>Abonne-toi sur ta plateforme préférée pour ne manquer aucune explication.</p>
        <ul class="cta-links">
{chr(10).join(f'          <li><a class="btn {"btn-primary" if k == "youtube" else "btn-ghost"}" href="{u}" target="_blank" rel="me noopener"><svg class="icon" aria-hidden="true" focusable="false"><use href="#i-{k}"/></svg>{n}<span class="sr-only"> (nouvel onglet)</span></a></li>' for k, n, u in SOCIALS)}
        </ul>
      </section>
    </div>"""
    out = PUBLIC / "articles" / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(head_html, main, scripts=("/assets/js/copy-link.js",)), encoding="utf-8")
    return list(dict.fromkeys(used))


def card(art, sizes, level):
    slug = art["slug"]
    cover = art["cover"]
    minutes = reading_minutes(art["body"])
    return f"""          <li>
            <article class="article-card">
              <a class="article-card-link" href="/articles/{slug}/">
                {img_tag(art, cover, sizes, "(min-width: 960px) 360px, (min-width: 640px) 45vw, 92vw")}
                <span class="article-card-body">
                  <span class="kicker">{esc(art["category"])} · Vidéo et article</span>
                  <h{level} class="article-card-title">{esc(art["title"])}</h{level}>
                  <span class="article-card-text">{esc(art["description"])}</span>
                  <span class="article-card-meta">{minutes} min de lecture · vidéo de {fmt_duration(art["video"]["duration_seconds"])}</span>
                </span>
              </a>
            </article>
          </li>"""


def list_page(arts, sizes):
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Accueil", "item": f"{SITE}/"},
                {"@type": "ListItem", "position": 2, "name": "Articles", "item": f"{SITE}/articles/"}]},
            {"@type": "CollectionPage", "@id": f"{SITE}/articles/#page", "url": f"{SITE}/articles/", "name": "Articles",
             "inLanguage": "fr-FR", "isPartOf": {"@id": f"{SITE}/#website"}, "publisher": {"@id": ORG_ID},
             "mainEntity": {"@type": "ItemList", "itemListElement": [
                 {"@type": "ListItem", "position": i, "url": f"{SITE}/articles/{a['slug']}/", "name": a["title"]}
                 for i, a in enumerate(arts, 1)]}},
        ],
    }
    desc = "Les articles d'Une Minute Pour Comprendre : chaque vidéo développée en texte, avec ses images, ses explications et les sources scientifiques utilisées."
    head_html = head("Articles | Une Minute Pour Comprendre", desc, "/articles/", "website",
                     f"/assets/img/articles/{arts[0]['slug']}/og.jpg", ld, og_alt=arts[0]["images"][arts[0]["cover"]]["alt"])
    cards = "\n".join(card(a, sizes[a["slug"]], 2) for a in arts)
    main = f"""    <div class="container article-wrap">
      <nav class="breadcrumb" aria-label="Fil d'Ariane">
        <ol>
          <li><a href="/">Accueil</a></li>
          <li aria-current="page">Articles</li>
        </ol>
      </nav>
      <section class="section article-list" aria-labelledby="articles-title">
        <div class="section-head">
          <p class="kicker">Les articles</p>
          <h1 id="articles-title" class="section-title">Les vidéos, <span class="accent">en version lisible</span></h1>
          <p class="section-intro">Chaque article développe une vidéo de la chaîne : la vidéo d'abord, puis le mécanisme expliqué pas à pas, les limites de ce qu'on sait et les sources scientifiques utilisées.</p>
        </div>
        <ul class="article-grid">
{cards}
        </ul>
      </section>
    </div>"""
    out = PUBLIC / "articles"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(head_html, main), encoding="utf-8")


def not_found_page():
    head_html = head("Page introuvable | Une Minute Pour Comprendre", "Cette page n'existe pas ou a été déplacée.",
                     "/404.html", "website", "/assets/img/og-image.jpg", robots="noindex, follow")
    main = """    <div class="container not-found">
      <p class="kicker">Erreur 404</p>
      <h1 class="section-title">Page introuvable, <span class="accent">mais pas la curiosité</span></h1>
      <p class="section-intro">Cette page n'existe pas ou a été déplacée. Retrouve les vidéos et les articles depuis l'accueil.</p>
      <p class="not-found-actions">
        <a class="btn btn-primary" href="/">Retour à l'accueil</a>
        <a class="btn btn-ghost" href="/articles/">Voir les articles</a>
      </p>
    </div>"""
    (PUBLIC / "404.html").write_text(page(head_html, main, current_articles=False), encoding="utf-8")


def update_home(arts, sizes):
    path = PUBLIC / "index.html"
    text = path.read_text(encoding="utf-8")
    cards = "\n".join(card(a, sizes[a["slug"]], 3) for a in arts[:3])
    block = f"""<!-- articles:start -->
    <section class="section articles-home" id="articles" aria-labelledby="articles-home-title">
      <div class="container">
        <div class="section-head">
          <p class="kicker">Les articles</p>
          <h2 id="articles-home-title" class="section-title">Va plus loin, <span class="accent">texte et sources</span></h2>
          <p class="section-intro">Chaque vidéo développée en article : le mécanisme expliqué pas à pas, ses limites et les publications scientifiques utilisées.</p>
        </div>
        <ul class="article-grid">
{cards}
        </ul>
        <p class="articles-more"><a class="btn btn-ghost" href="/articles/">Tous les articles</a></p>
      </div>
    </section>
    <!-- articles:end -->"""
    new, n = re.subn(r"<!-- articles:start -->.*?<!-- articles:end -->", lambda _: block, text, flags=re.S)
    if n != 1:
        raise SystemExit("Marqueurs <!-- articles:start/end --> introuvables dans public/index.html")
    new = re.sub(r'href="(?:/)?assets/css/style\.css(?:\?v=\w+)?"', lambda _: f'href="{asset("/assets/css/style.css")[1:]}"', new)
    new = re.sub(r'src="(?:/)?assets/js/site\.js(?:\?v=\w+)?"', lambda _: f'src="{asset("/assets/js/site.js")[1:]}"', new)
    path.write_text(new, encoding="utf-8")


def write_sitemap(arts, sizes, used):
    """sitemap.xml : accueil, liste et articles ; chaque article déclare les images de son texte."""
    latest = max([a["modified"] for a in arts] + ["2026-09-30"])
    entries = [(f"{SITE}/", latest, []), (f"{SITE}/articles/", latest, [])]
    for a in arts:
        slug = a["slug"]
        imgs = [f"{SITE}{img_url(slug, k, sizes[slug][k][-1][0])}" for k in used[slug]]
        entries.append((f"{SITE}/articles/{slug}/", a["modified"], imgs))
    body = "\n".join(
        f"  <url>\n    <loc>{u}</loc>\n    <lastmod>{d}</lastmod>\n"
        + "".join(f"    <image:image><image:loc>{i}</image:loc></image:image>\n" for i in imgs) + "  </url>"
        for u, d, imgs in entries)
    (PUBLIC / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        f'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n{body}\n</urlset>\n', encoding="utf-8")


def write_feed(arts):
    """feed.xml : flux RSS 2.0 des articles (découverte et réutilisation par les agrégateurs)."""
    def rfc822(iso):
        return format_datetime(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc))
    items = "\n".join(
        f"""    <item>
      <title>{esc(a["title"])}</title>
      <link>{SITE}/articles/{a["slug"]}/</link>
      <guid isPermaLink="true">{SITE}/articles/{a["slug"]}/</guid>
      <pubDate>{rfc822(a["published"])}</pubDate>
      <category>{esc(a["category"])}</category>
      <description>{esc(a["description"])}</description>
    </item>""" for a in arts)
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{esc(FEED_TITLE)}</title>
    <link>{SITE}/articles/</link>
    <atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml"/>
    <description>{esc(SITE_DESC)}</description>
    <language>fr-FR</language>
    <lastBuildDate>{rfc822(max(a["modified"] for a in arts))}</lastBuildDate>
{items}
  </channel>
</rss>
"""
    (PUBLIC / "feed.xml").write_text(feed, encoding="utf-8")


def write_llms_txt(arts):
    """llms.txt : présentation courte du site et de ses pages clés, lisible par les moteurs de réponse IA."""
    lines = [
        "# Une Minute Pour Comprendre", "",
        f"> {SITE_DESC}", "",
        "Site officiel de la chaîne @1min.pour.comprendre. Chaque vidéo suit trois temps : le phénomène, le mécanisme, la réponse. "
        "Les articles développent les vidéos, indiquent les limites de ce que l'on sait et citent les publications scientifiques utilisées. "
        "Un projet Zone IA (https://zoneia.fr).", "",
        "## Articles", "",
        *[f"- [{a['title']}]({SITE}/articles/{a['slug']}/): {a['description']}" for a in arts], "",
        "## Pages et chaîne", "",
        f"- [Accueil]({SITE}/): présentation de la chaîne, des quatre univers (science, animaux, corps humain, nature) et des réseaux",
        f"- [Tous les articles]({SITE}/articles/): liste des articles, un par vidéo",
        f"- [Flux RSS]({SITE}/feed.xml): nouveaux articles",
        f"- [YouTube]({CHANNEL}): plateforme principale, Shorts et formats longs",
        *[f"- [{n}]({u}): même nom, @1min.pour.comprendre" for k, n, u in SOCIALS if k != "youtube"], "",
    ]
    (PUBLIC / "llms.txt").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", action="store_true", help="régénérer toutes les images")
    args = parser.parse_args()
    arts = load_articles()
    if not arts:
        raise SystemExit("Aucun article dans content/articles/")
    sizes = {a["slug"]: build_images(a, args.images) for a in arts}
    used = {a["slug"]: article_page(a, sizes[a["slug"]], [(o, sizes[o["slug"]]) for o in arts if o is not a]) for a in arts}
    list_page(arts, sizes)
    not_found_page()
    update_home(arts, sizes)
    write_sitemap(arts, sizes, used)
    write_feed(arts)
    write_llms_txt(arts)
    outputs = [PUBLIC / "404.html", PUBLIC / "sitemap.xml", PUBLIC / "feed.xml", PUBLIC / "llms.txt"]
    for p in sorted((PUBLIC / "articles").rglob("*.html")) + outputs:
        print(f"{p.stat().st_size / 1024:7.1f} Ko  {p.relative_to(PUBLIC)}")


if __name__ == "__main__":
    main()
