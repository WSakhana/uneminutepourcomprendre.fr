"""Publie les brouillons prêts quand YouTube les confirme publics. Aucune écriture YouTube.

Sans --publish : contrôle et suivi uniquement. --publish réutilise le build, check, SFTP,
verify_live et IndexNow existants. Une date passée ne vaut jamais un statut public.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.request import urlopen
from youtube_readonly import inventory

ROOT = Path(__file__).resolve().parent.parent
TRACK = ROOT / 'tracking'
STATE = TRACK / 'sync-state.local.json'
PARIS = ZoneInfo('Europe/Paris')


def eligible(meta, videos):
    required = [meta.get('video', {}), *meta.get('additional_videos', [])]
    ids = [v.get('id') for v in required]
    return bool(meta.get('ready', True) and ids and all(
        id and id in videos and videos[id]['status'].get('privacyStatus') == 'public'
        and videos[id]['status'].get('embeddable') is True
        and videos[id]['status'].get('uploadStatus') == 'processed'
        and videos[id]['snippet'].get('liveBroadcastContent', 'none') == 'none'
        for id in ids))


def replace_scalar(text, key, value):
    line = key + ' = ' + json.dumps(value, ensure_ascii=False)
    # Les champs racine ne doivent pas être confondus avec ceux de [video].
    first, sep, tables = text.partition('\n[')
    if re.search(r'^' + re.escape(key) + r'\s*=', first, re.M):
        first = re.sub(r'^' + re.escape(key) + r'\s*=.*$', lambda _: line, first, count=1, flags=re.M)
    else:
        first += '\n' + line
    return first + sep + tables


def resolve_missing_id(meta, videos, assigned):
    """Associe uniquement un nom de fichier d’upload unique et une durée cohérente, jamais un titre flou."""
    if meta.get('video', {}).get('id') or not meta.get('editorial_ready'):
        return None
    key = meta.get('project_key', '')
    match = re.fullmatch(r'(short|original|long)-(\d+)', key)
    if not match:
        return None
    number = int(match[2])
    exact = Path(meta.get('video_file', '')).name
    prefix = (r'^UMPC-R\s+' if match[1] == 'short' else r'^UMPC\s+') + str(number) + r'\s+-' if match[1] != 'long' else None
    candidates = []
    for id, v in videos.items():
        name = v.get('fileDetails', {}).get('fileName', '')
        if id in assigned or not name or not (name == exact or (prefix and re.match(prefix, name, re.I))):
            continue
        duration = re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?', v['contentDetails']['duration'])
        seconds = sum(float(x or 0) * factor for x, factor in zip(duration.groups(), (3600, 60, 1))) if duration else 0
        if abs(seconds - meta['video'].get('duration_seconds', 0)) <= 2:
            candidates.append(v)
    return candidates[0] if len(candidates) == 1 else None


def run_tool(name, *args):
    result = subprocess.run([sys.executable, str(ROOT / 'tools' / name), *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    # Les outils existants ne journalisent pas les identifiants. Garder seulement la fin.
    if result.returncode:
        raise RuntimeError(f'{name} : échec {result.returncode}\n' + result.stdout[-3000:] + result.stderr[-1500:])
    print(result.stdout[-1800:].rstrip())


def public_digest():
    digest = hashlib.sha256()
    for p in sorted((ROOT / 'public').rglob('*')):
        if p.is_file():
            digest.update(p.relative_to(ROOT / 'public').as_posix().encode())
            digest.update(p.read_bytes())
    return digest.hexdigest()


@contextmanager
def lock():
    import msvcrt
    TRACK.mkdir(exist_ok=True)
    with (TRACK / 'sync.lock.local').open('a+b') as f:
        f.seek(0)
        if f.read(1) == b'':
            f.write(b'0'); f.flush()
        f.seek(0)
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('Une synchronisation est déjà en cours')
        try:
            yield
        finally:
            f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def atomic_json(path, data):
    tmp = path.with_suffix('.tmp.local')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def synchronize(publish=False, force=False, prepare=False):
    snap = inventory()  # Échec API : aucune promotion ni aucun envoi.
    videos = {v['id']: v for v in snap['videos']}
    paths = sorted((ROOT / 'content/articles').glob('*/article.toml'))
    existing = [tomllib.loads(p.read_text(encoding='utf-8')) for p in paths]
    assigned = {v.get('id') for m in existing for v in [m.get('video', {}), *m.get('additional_videos', [])] if v.get('id')}
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    records = []
    candidates, inactive = [], []
    seen = {}
    for path in paths:
        meta = tomllib.loads(path.read_text(encoding='utf-8'))
        resolved = resolve_missing_id(meta, videos, assigned)
        if resolved and (publish or prepare):
            text = path.read_text(encoding='utf-8')
            text = re.sub(r'(\[video\]\s*\nid\s*=)\s*[^\n]*', lambda m: m[1] + ' ' + json.dumps(resolved['id']), text, count=1)
            thumb = resolved['snippet']['thumbnails']
            thumb_url = next(thumb[k]['url'] for k in ('maxres', 'standard', 'high', 'default') if k in thumb)
            with urlopen(thumb_url, timeout=30) as response:
                (path.parent / 'youtube-thumbnail.jpg').write_bytes(response.read())
            text = replace_scalar(text, 'ready', True)
            text = replace_scalar(text, 'title', resolved['snippet']['title'])
            text = re.sub(r'(\[video\].*?\ntitle\s*=)\s*[^\n]*', lambda m: m[1] + ' ' + json.dumps(resolved['snippet']['title'], ensure_ascii=False), text, count=1, flags=re.S)
            text = replace_scalar(text, 'thumbnail_source', thumb_url)
            text = replace_scalar(text, 'publication_blocker', '')
            text = replace_scalar(text, 'identity_evidence', 'Nom de fichier d’upload unique et durée cohérente sur la chaîne authentifiée')
            path.write_text(text, encoding='utf-8')
            meta = tomllib.loads(text)
            assigned.add(resolved['id'])
        ids = [v.get('id') for v in [meta.get('video', {}), *meta.get('additional_videos', [])] if v.get('id')]
        for id in ids:
            if id in seen:
                raise RuntimeError('Doublon d’identifiant YouTube : ' + id)
            seen[id] = meta['slug']
        valid = eligible(meta, videos)
        published = meta.get('status', 'published') == 'published'
        if valid:
            if not published:
                candidates.append(meta['slug'])
        else:
            inactive.append(meta['slug'])
        if (publish or prepare) and (valid != published):
            text = replace_scalar(path.read_text(encoding='utf-8'), 'status', 'published' if valid else 'draft')
            if valid:
                date = videos[ids[0]]['snippet']['publishedAt']
                date = datetime.fromisoformat(date.replace('Z', '+00:00')).astimezone(PARIS).date().isoformat()
                text = replace_scalar(text, 'published', date)
                # La date de la vidéo correspond à la mise en ligne effective, jamais à l’upload privé.
                text = re.sub(r'^(upload_date\s*=)\s*.*$', lambda m: m[1] + ' ' + json.dumps(date), text, count=1, flags=re.M)
                text = replace_scalar(text, 'modified', datetime.now(PARIS).date().isoformat())
            else:
                page = ROOT / 'public/articles' / meta['slug']
                if page.exists():
                    archive = ROOT / 'tmp/inactive-pages' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') / meta['slug']
                    archive.parent.mkdir(parents=True, exist_ok=True)
                    if not page.resolve().is_relative_to((ROOT / 'public/articles').resolve()):
                        raise RuntimeError('Chemin de page hors public/articles')
                    page.replace(archive)  # Archive locale ; aucune suppression de données.
            path.write_text(text, encoding='utf-8')
            meta = tomllib.loads(text)
        details = [videos[id] for id in ids if id in videos]
        records.append({'project_key': meta.get('project_key'), 'project_keys': meta.get('project_keys', [meta.get('project_key')]), 'project': meta.get('production'), 'youtube_ids': ids,
            'youtube': [{'id': v['id'], 'title': v['snippet']['title'], 'privacy': v['status']['privacyStatus'], 'scheduled_at': v['status'].get('publishAt'), 'published_at': v['snippet']['publishedAt'] if v['status']['privacyStatus'] == 'public' else None, 'embeddable': v['status'].get('embeddable')} for v in details],
            'article_url': f"https://uneminutepourcomprendre.fr/articles/{meta['slug']}/", 'slug': meta['slug'],
            'article_status': meta.get('status', 'published'), 'eligible': valid, 'ready': meta.get('ready', True),
            'youtube_original_descriptions': {v['id']: v['snippet']['description'] for v in details},
            'publication_blocker': meta.get('publication_blocker', ''),
            'sources_status': meta.get('sources_status', 'références et limites documentées'), 'credits_status': meta.get('credits_status', 'voir crédits et registre des médias'),
            'youtube_description': meta.get('youtube_description', ''), 'checked_at': snap['checked_at']})
    if publish or prepare:
        # Refuser aussi l’accès à des pages distantes devenues privées : le SFTP ne supprime rien.
        htaccess = ROOT / 'public/.htaccess'
        text = htaccess.read_text(encoding='utf-8')
        block = '# youtube-drafts:start\n' + '\n'.join('RewriteRule ^(?:articles|assets/img/articles)/' + re.escape(slug) + '(?:/|$) - [R=404,L]' for slug in sorted(inactive)) + '\n# youtube-drafts:end'
        if '# youtube-drafts:start' in text:
            text = re.sub(r'# youtube-drafts:start.*?# youtube-drafts:end', lambda _: block, text, flags=re.S)
        else:
            text = re.sub(r'(RewriteEngine\s+On)', lambda m: m[0] + '\n' + block, text, count=1, flags=re.I)
            if '# youtube-drafts:start' not in text:
                raise RuntimeError('RewriteEngine absent : protection des brouillons non installée')
        htaccess.write_text(text, encoding='utf-8')
        run_tool('build_articles.py')
        run_tool('check_site.py')
        digest = public_digest()
        if publish and (force or state.get('deployed_digest') != digest):
            if not all(os.environ.get(k) for k in ('UMPC_SFTP_HOST', 'UMPC_SFTP_USER', 'UMPC_SFTP_PASSWORD')):
                raise RuntimeError('Variables SFTP absentes ; aucune demande interactive de mot de passe')
            run_tool('deploy_sftp.py', '--dry-run')
            # Lecture fraîche juste avant l’envoi ; si une visibilité vient de changer, reprendre au prochain passage.
            fresh = inventory()
            fresh_videos = {v['id']: v for v in fresh['videos']}
            for path in (ROOT / 'content/articles').glob('*/article.toml'):
                meta = tomllib.loads(path.read_text(encoding='utf-8'))
                if meta.get('status', 'published') == 'published' and not eligible(meta, fresh_videos):
                    raise RuntimeError('Statut YouTube changé avant envoi : ' + meta['slug'])
            run_tool('deploy_sftp.py')
            run_tool('verify_live.py')
            run_tool('verify_article_publication.py')
            pages = {p.parent.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'public/articles').glob('*/index.html')}
            state.update({'deployed_digest': digest, 'deployed_at': datetime.now(timezone.utc).isoformat(), 'deployed_articles': pages})
            atomic_json(STATE, state)  # Succès marqué seulement après vérification ; les échecs seront repris.
            try:
                run_tool('indexnow.py')
                state['indexnow_pending'] = False
            except RuntimeError:
                state['indexnow_pending'] = True
                print('INDEXNOW_PENDING : envoi SFTP et vérification réussis, notification à reprendre.')
        elif publish and state.get('indexnow_pending'):
            run_tool('indexnow.py'); state['indexnow_pending'] = False
        if publish:
            state['last_success_at'] = datetime.now(timezone.utc).isoformat()
            state.pop('last_error', None)
            atomic_json(STATE, state)
    for r in records:
        page = ROOT / 'public/articles' / r['slug'] / 'index.html'
        verified = page.exists() and state.get('deployed_articles', {}).get(r['slug']) == hashlib.sha256(page.read_bytes()).hexdigest()
        r['publication_verified_at'] = state.get('deployed_at') if r['article_status'] == 'published' and verified else None
        r['description_update_ready'] = bool(r['publication_verified_at'] and r['eligible'] and r['youtube_description'] and 'partiels' not in r['credits_status'])
    atomic_json(TRACK / 'articles.private.json', {'checked_at': snap['checked_at'], 'channel_id': snap['channel_id'], 'records': records, 'candidates': candidates, 'unmatched_youtube_ids': sorted(set(videos) - set(seen))})
    print(f'{len(records)} articles suivis ; {len(candidates)} brouillons prêts avec vidéo publique ; envoi={publish}.')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--prepare', action='store_true', help='préparer les pages locales éligibles, sans envoi SFTP')
    args = parser.parse_args()
    with lock():
        try:
            synchronize(args.publish, args.force, args.prepare)
        except Exception as e:
            state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
            # Type et message contrôlé, jamais le corps d’une réponse OAuth ni les secrets.
            error = str(e) if isinstance(e, RuntimeError) else type(e).__name__
            state.update({'last_error': error, 'last_error_at': datetime.now(timezone.utc).isoformat()})
            atomic_json(STATE, state)
            print('SYNC_FAILED : ' + error, file=sys.stderr)
            raise SystemExit(1)


if __name__ == '__main__':
    main()
