"""Inventorie le dossier de production d'une vidéo UMPC pour préparer son article de site.

Usage (depuis la racine du dépôt du site) :
  py -3 .agents/skills/umpc-site-article/scripts/inspect_production.py \\
      --production "D:/@UMPC-Long/Videos/3 - Les capacites etonnantes des bacteries" \\
      --youtube "https://youtu.be/PwoQaj9kHKQ" [--slug mon-slug] [--write-draft] [--force] [--no-network]

Lecture seule par défaut : le rapport Markdown est écrit sur la sortie standard. Avec --write-draft, le script crée
content/articles/<slug>/article.toml (brouillon avec des « TODO » à remplir) ; le générateur du site refuse de
construire une page tant qu'il reste un TODO.

Le script extrait ce qui est fiable (identifiant YouTube, chapitres, tableaux de médias et de droits, sources citées,
narration par scène, images candidates). Il ne rédige pas l'article : les formats des documents varient d'un épisode à
l'autre, donc tout ce qui est ambigu est affiché tel quel pour que l'agent le lise et décide.
"""
import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(__file__).resolve().parents[4]
URL_RE = re.compile(r"https?://[^\s)>\]|`]+")


# ----------------------------------------------------------------------------- utilitaires


def read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def youtube_id(url):
    m = re.search(r"(?:youtu\.be/|[?&]v=|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})", url)
    if not m:
        raise SystemExit(f"Identifiant YouTube introuvable dans : {url}")
    return m.group(1)


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text[:60].rstrip("-")


def short_key(stem, taken):
    """Clé d'image courte et lisible (snake_case, 28 caractères au plus), unique parmi `taken`."""
    stem = re.sub(r"[_-]?\d{5,}$", "", stem.lower())
    stem = re.sub(r"(^|_)(wikimedia|codex)(?=_|$)", "", stem)
    key = ""
    for w in (w for w in re.split(r"[^a-z0-9]+", stem) if w):
        if len(key) + len(w) + 1 > 28:
            break
        key = f"{key}_{w}" if key else w
    key = key or "image"
    base, n = key, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    taken.add(key)
    return key


def toml_str(value):
    return json.dumps(value, ensure_ascii=False)


def strip_md(text):
    return re.sub(r"[`*_]", "", text).strip()


def oembed(video_id):
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def published_thumbnail(video_id, prod):
    """Compare la miniature YouTube publiée aux fichiers Montage/*miniature*.png ; renvoie [(écart moyen, fichier)] trié."""
    try:
        from PIL import Image, ImageChops, ImageStat
    except ImportError:
        return None
    ref = None
    for name in ("maxresdefault", "hqdefault"):
        try:
            req = urllib.request.Request(f"https://i.ytimg.com/vi/{video_id}/{name}.jpg", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                ref = Image.open(io.BytesIO(r.read())).convert("L")
            if name == "hqdefault":  # 4:3 avec bandes noires : garder la zone 16:9
                ref = ref.crop((0, round(ref.height * 0.125), ref.width, round(ref.height * 0.875)))
            break
        except Exception:
            continue
    if ref is None:
        return None
    ref = ref.resize((160, 90))
    out = []
    for f in sorted((prod / "Montage").glob("*miniature*.png")):
        im = Image.open(f).convert("L").resize((160, 90))
        out.append((ImageStat.Stat(ImageChops.difference(ref, im)).mean[0], f.relative_to(prod).as_posix()))
    return sorted(out)


def ffprobe_duration(path):
    exe = shutil.which("ffprobe")
    if not exe or not Path(path).exists():
        return None
    out = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def image_size(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


# ----------------------------------------------------------------------------- extraction des documents


def parse_title(social):
    lines = social.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^#+\s*Titre", line, re.I):
            for nxt in lines[i + 1:]:
                if nxt.strip() and not nxt.startswith("#"):
                    return strip_md(nxt)
    m = re.search(r"^#\s+(.+)$", social, re.M)
    return strip_md(m.group(1)) if m else ""


def parse_chapters(social):
    chapters = []
    for line in social.splitlines():
        m = re.match(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s+(.+?)\s*$", line)
        if m:
            h, mn, s = (int(m.group(1)), int(m.group(2)), m.group(3))
            seconds = h * 3600 + mn * 60 + int(s) if s else h * 60 + mn
            chapters.append({"t": seconds, "label": strip_md(m.group(4))})
    return chapters


def parse_description(social):
    lines = social.splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(r"^#+\s*Description", l, re.I)), None)
    if start is None:
        return []
    paras, cur = [], []
    for line in lines[start + 1:]:
        if line.startswith("#") or re.search(r"Chapitres", line) or re.match(r"^\s*\d{1,2}:\d{2}\s", line):
            break
        if line.strip():
            cur.append(line.strip())
        elif cur:
            paras.append(" ".join(cur))
            cur = []
    if cur:
        paras.append(" ".join(cur))
    return paras


def parse_social_sources(social):
    """Lignes « - ... » avec une URL, dans le bloc « Sources » de la description YouTube."""
    lines = social.splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(r"^\s*Sources?\s*:?\s*$", strip_md(l))), None)
    out = []
    if start is None:
        return out
    for line in lines[start + 1:]:
        if line.startswith("- "):
            urls = URL_RE.findall(line)
            if not urls:
                continue
            body = line[2:]
            if "|" in body:
                parts = [p.strip() for p in body.split("|")]
                out.append({"citation": parts[0], "topic": parts[1] if len(parts) > 2 else "", "url": urls[-1]})
            else:
                out.append({"citation": re.sub(r"\s*:?\s*https?://\S+\s*$", "", body).strip(), "topic": "", "url": urls[-1]})
        elif line.strip() and not line.startswith("-"):
            if out:
                break
    return out


def parse_research_sources(research):
    out = []
    for line in research.splitlines():
        m = re.match(r"^\s*[-*]\s*\*\*(S\d+)\.?\*\*\s*\.?\s*(.+)$", line)
        if m:
            out.append({"id": m.group(1), "text": strip_md(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m.group(2))),
                        "urls": URL_RE.findall(m.group(2)), "dois": re.findall(r"10\.\d{4,9}/[^\s,;)\]]+", m.group(2))})
    return out


def parse_tables(text):
    """Toutes les tables Markdown : liste de listes de dict {en-tête: cellule}."""
    tables, cur = [], []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            cur.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif cur:
            tables.append(cur)
            cur = []
    if cur:
        tables.append(cur)
    result = []
    for t in tables:
        if len(t) < 3 or not all(set(c) <= set("-: ") for c in t[1]):
            continue
        head = t[0]
        result.append([dict(zip(head, row)) for row in t[2:] if len(row) >= 2])
    return result


def parse_media_sources(text):
    rows = []
    for table in parse_tables(text):
        for row in table:
            first = next(iter(row.values()), "")
            m = re.search(r"`([^`]+)`", first)
            fname = m.group(1) if m else first
            rows.append({"file": fname, "cells": row, "urls": URL_RE.findall(" ".join(row.values()))})
    return rows


def parse_scenes(narration):
    clean = narration.split("## Clean narration", 1)
    text = clean[1] if len(clean) == 2 else narration
    scenes = {}
    for m in re.finditer(r"^###\s+Sc[eè]ne\s+(\d+)\s*$\n+(.*?)(?=^###|\Z)", text, re.M | re.S):
        scenes[int(m.group(1))] = m.group(2).strip()
    return scenes


def parse_facts_table(script):
    for table in parse_tables(script):
        if any("Source" in k for k in table[0]) and any("Affirmation" in k for k in table[0]):
            return table
    return []


def headings(text, levels=(2, 3)):
    return [(len(m.group(1)), m.group(2).strip()) for m in re.finditer(r"^(#{2,3})\s+(.+)$", text, re.M) if len(m.group(1)) in levels]


# ----------------------------------------------------------------------------- inventaire des fichiers


def list_files(prod):
    items = []
    for pattern, kind in (("media/images/*", "image média (voir MediaSources.md pour les droits)"),
                          ("Scenes/Scene-*/*frame*.png", "image de scène générée (illustration)"),
                          ("Montage/*miniature*.png", "miniature"),
                          ("Montage/Hyperframes/assets/brand/*.png", "marque")):
        for f in sorted(prod.glob(pattern)):
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
                items.append({"path": f.relative_to(prod).as_posix(), "kind": kind, "bytes": f.stat().st_size,
                              "size": image_size(f) if f.suffix.lower() != ".svg" else None})
    return items


def final_video(prod):
    cands = [p for p in sorted((prod / "Montage").glob("*.mp4")) if "brouillon" not in p.name.lower()]
    final = [p for p in cands if "final" in p.name.lower()] or cands
    return final[0] if final else None


# ----------------------------------------------------------------------------- brouillon article.toml


def draft_toml(slug, title, video_id, prod, final, duration, chapters, media_rows, social_sources, upload_date):
    L = []
    add = L.append
    add(f"slug = {toml_str(slug)}")
    add(f"title = {toml_str(title or 'TODO')}")
    add('short_title = "TODO"  # 4 à 6 mots, utilisé dans le fil d\'Ariane')
    add('category = "Science"')
    add('description = "TODO"  # 160 caractères maximum (meta description)')
    add('lead = "TODO"  # chapô : pose la question de la vidéo en 2 ou 3 phrases')
    add(f'published = {toml_str(upload_date)}  # VÉRIFIER : date réelle de mise en ligne de la vidéo')
    add(f'modified = {toml_str(date.today().isoformat())}')
    add('cover = "TODO"  # clé d\'une image ci-dessous ; idéalement la miniature réellement publiée sur YouTube')
    add(f"production = {toml_str(prod.as_posix())}")
    if final:
        add(f"video_file = {toml_str(final.relative_to(prod).as_posix())}")
    add('# method = "..."  # note de méthode facultative (accès aux sources, illustrations)')
    add("")
    add("[video]")
    add(f"id = {toml_str(video_id)}")
    add(f"title = {toml_str(title or 'TODO')}")
    add(f"duration_seconds = {duration if duration else toml_str('TODO')}")
    add(f"upload_date = {toml_str(upload_date)}  # VÉRIFIER")
    add("")
    for c in chapters:
        add("[[chapters]]")
        add(f"t = {c['t']}")
        add(f"label = {toml_str(c['label'])}")
    add("")
    add("# Images : ne garder que celles qui servent l'article. Pour une image extraite de la vidéo finale,")
    add('# remplacer src par video_time = <secondes> (et box = [x0, y0, x1, y1] pour recadrer).')
    seen, keys = set(), set()
    for row in media_rows:
        f = row["file"]
        text = " ".join(row["cells"].values())
        # Écartées : formats non raster, références de génération et médias « non affichés » dans la vidéo.
        if (not f.startswith("images/") or f in seen or f.lower().endswith(".svg")
                or re.search(r"non affich|référence[s]? de (sujet|génération)", text, re.I)):
            continue
        seen.add(f)
        key = short_key(Path(f).stem, keys)
        cells = row["cells"]
        credit = next((v for k, v in cells.items() if k.lower().startswith("crédit") or k.lower().startswith("credit")), "")
        rights = next((v for k, v in cells.items() if k.lower().startswith("droits")), "")
        url = row["urls"][0] if row["urls"] else ""
        generated = bool(re.search(r"codex|génér|illustration", " ".join(cells.values()), re.I)) and "wikimedia" not in f
        add("")
        add(f"[images.{key}]")
        add(f"src = {toml_str('media/' + f)}")
        add('alt = "TODO"  # description visuelle factuelle')
        add('caption = "TODO"')
        credit_clean = strip_md(re.sub(r"\(https?://[^)]*\)|[\[\]]", "", credit or rights)) or "TODO"
        add(f"credit = {toml_str(credit_clean)}  # à relire")
        if url:
            add(f"credit_url = {toml_str(url)}")
        if generated:
            add("generated = true")
    add("")
    add("# Sources : uniquement celles qui justifient une affirmation de la vidéo (publication originale en priorité).")
    add("# Les ids S1, S2... sont propres à cet article (ordre d'affichage) : ils ne correspondent pas aux S1..Sn de Research.md.")
    for i, s in enumerate(social_sources, 1):
        add("")
        add("[[sources]]")
        add(f'id = "S{i}"')
        add(f'authors = "TODO"  # d\'après la description : {s["citation"]}')
        add('title = "TODO"')
        add('publication = "TODO"')
        add('year = "TODO"')
        add(f'topic = {toml_str(s["topic"] or "TODO")}')
        add(f"url = {toml_str(s['url'])}")
        add('kind = "Étude originale"  # ou « Présentation institutionnelle », « Contexte »')
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------- rapport


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--production", required=True, help="dossier de production de la vidéo")
    ap.add_argument("--youtube", required=True, help="URL YouTube de la vidéo")
    ap.add_argument("--slug", help="slug de l'article (sinon déduit du titre)")
    ap.add_argument("--write-draft", action="store_true", help="écrire content/articles/<slug>/article.toml (brouillon)")
    ap.add_argument("--force", action="store_true", help="écraser un article.toml existant")
    ap.add_argument("--no-network", action="store_true", help="ne pas interroger YouTube (oEmbed)")
    args = ap.parse_args()

    prod = Path(args.production)
    if not prod.is_dir():
        raise SystemExit(f"Dossier de production introuvable : {prod}")
    vid = youtube_id(args.youtube)
    docs = prod / "Documents"
    social, research = read(docs / "Social_Publishing.md"), read(docs / "Research.md")
    narration, script = read(docs / "Narration.md"), read(docs / "Script_Video.md")
    media = read(prod / "media" / "MediaSources.md")

    meta = None if args.no_network else oembed(vid)
    title = (meta or {}).get("title") or parse_title(social)
    slug = args.slug or slugify(title or prod.name)
    final = final_video(prod)
    duration = ffprobe_duration(final) if final else None
    chapters = parse_chapters(social)
    description = parse_description(social)
    social_sources = parse_social_sources(social)
    research_sources = parse_research_sources(research)
    media_rows = parse_media_sources(media)
    scenes = parse_scenes(narration)
    facts = parse_facts_table(script)
    files = list_files(prod)
    existing = REPO / "content" / "articles" / slug / "article.toml"

    out = []
    p = out.append
    p(f"# Inventaire : {prod.name}\n")
    p(f"- Vidéo YouTube : https://youtu.be/{vid} (id `{vid}`)")
    p(f"- Titre YouTube (oEmbed, fait foi : apostrophes typographiques) : {(meta or {}).get('title') or '(non récupéré)'}  |  titre dans Social_Publishing.md : {parse_title(social) or '(absent)'}")
    p(f"- Chaîne : {(meta or {}).get('author_name') or '(non récupérée)'}")
    p(f"- Slug proposé : `{slug}`  |  article existant : {'OUI, ' + str(existing.relative_to(REPO)) if existing.exists() else 'non'}")
    p(f"- Vidéo finale : {final.relative_to(prod).as_posix() if final else 'introuvable'}  |  durée mesurée : {f'{duration:.1f} s' if duration else 'inconnue'}")
    p("- Date de mise en ligne : INCONNUE (oEmbed ne la donne pas) : à demander ou à vérifier, ne pas inventer\n")

    p("\n## Miniature réellement publiée sur YouTube")
    ranking = None if args.no_network else published_thumbnail(vid, prod)
    if ranking:
        for i, (diff, f) in enumerate(ranking):
            p(f"- {f}  écart {diff:.1f}" + ("  <- la plus proche : c'est la miniature publiée (à prendre pour `cover`)" if i == 0 and diff < 15 else ""))
        p("La miniature « recommandée » de Social_Publishing.md n'est pas forcément celle qui a été publiée : se fier à ce classement.")
    else:
        p("(non comparée : réseau coupé, Pillow absent ou aucune miniature dans Montage/) : la télécharger depuis "
          f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg et la comparer à l'œil, ou demander à l'utilisateur.")

    p(f"\n## Chapitres YouTube ({len(chapters)})")
    p("\n".join(f"- {c['t']:>4} s  {c['label']}" for c in chapters) or "(aucun chapitre trouvé dans Social_Publishing.md)")

    p(f"\n## Description YouTube ({len(description)} paragraphes)")
    p("\n\n".join(description) or "(absente)")

    p(f"\n## Sources citées dans la description YouTube ({len(social_sources)}) : base de la bibliographie")
    p("\n".join(f"- {s['citation']}  |  sujet : {s['topic'] or '?'}  |  {s['url']}" for s in social_sources) or "(aucune)")

    p(f"\n## Sources de Research.md ({len(research_sources)}) : niveau d'accès et limites à respecter")
    for s in research_sources:
        p(f"- **{s['id']}** {s['text'][:400]}\n  urls : {', '.join(s['urls']) or '-'}  doi : {', '.join(s['dois']) or '-'}")
    if not research_sources:
        p("(aucune source au format « **S1.** » : voici les lignes de Research.md qui contiennent une URL ou un DOI)")
        for line in research.splitlines():
            if URL_RE.search(line) or re.search(r"10\.\d{4,9}/", line):
                p("- " + line.strip()[:300])
    p("\nRelire Research.md en entier : chaque cas y a une rubrique « Limites » qui devient l'encadré « Ce qu'il ne faut pas en conclure ».")
    p("Sections de Research.md : " + " / ".join(h for _, h in headings(research)))

    p(f"\n## Affirmations vérifiées (Script_Video.md) : {len(facts)} lignes")
    for row in facts:
        p("- " + " | ".join(v.replace("\n", " ")[:260] for v in row.values()))

    p(f"\n## Narration par scène ({len(scenes)} scènes) : matière, pas texte à recopier")
    for n, t in scenes.items():
        p(f"- Scène {n} : {t}")

    p(f"\n## Médias et droits (MediaSources.md) : {len(media_rows)} lignes")
    for r in media_rows:
        p(f"- `{r['file']}`  ->  " + " | ".join(f"{k}: {v[:140]}" for k, v in list(r["cells"].items())[1:]))

    p(f"\n## Fichiers image candidats ({len(files)})")
    for f in files:
        dims = f"{f['size'][0]}x{f['size'][1]}" if f["size"] else "?"
        p(f"- {f['path']}  [{dims}, {f['bytes'] // 1024} Ko]  {f['kind']}")
    p("\nImages extractibles de la vidéo finale (schémas animés du montage) : `video_time` dans article.toml ; repérer les bons instants")
    p("avec une planche contact ffmpeg avant de choisir (les images à mi-animation sont souvent vides).")

    print("\n".join(out))

    if args.write_draft:
        if existing.exists() and not args.force:
            raise SystemExit(f"\nRefus d'écraser {existing} (utiliser --force).")
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text(draft_toml(slug, title, vid, prod, final, round(duration, 1) if duration else None,
                                       chapters, media_rows, social_sources, "TODO"), encoding="utf-8")
        print(f"\nBrouillon écrit : {existing.relative_to(REPO)} (créer aussi body.html ; le build refuse les TODO)")


if __name__ == "__main__":
    main()
