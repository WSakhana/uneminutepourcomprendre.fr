"""Lecture seule YouTube Data API avec le jeton DPAPI existant, jamais de mutation YouTube."""
import ctypes
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
AUTH_ROOT = Path(os.environ.get('UMPC_YOUTUBE_AUTH_DIR', 'G:/My Drive/@UMPC'))


class Blob(ctypes.Structure):
    _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def dpapi(data, decrypt=False):
    buf = ctypes.create_string_buffer(data)
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dst = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst)):
        raise RuntimeError('Jeton DPAPI inaccessible pour cet utilisateur Windows')
    try:
        return ctypes.string_at(dst.data, dst.size)
    finally:
        ctypes.windll.kernel32.LocalFree(dst.data)


def access_token():
    path = AUTH_ROOT / '.youtube_private/oauth.dpapi'
    data = json.loads(dpapi(path.read_bytes(), decrypt=True))
    if data.get('expires_at', 0) < time.time() + 120:
        cfg = json.loads((AUTH_ROOT / 'youtube_client_secret.json').read_text())['installed']
        body = urlencode({'client_id': cfg['client_id'], 'client_secret': cfg['client_secret'], 'refresh_token': data['refresh_token'], 'grant_type': 'refresh_token'}).encode()
        # URI fixe : les identifiants sont envoyés seulement au serveur OAuth de Google.
        req = Request('https://oauth2.googleapis.com/token', data=body, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        with urlopen(req, timeout=30) as r:
            data.update(json.load(r))
        data['expires_at'] = time.time() + data['expires_in']
        tmp = path.with_suffix('.tmp')
        tmp.write_bytes(dpapi(json.dumps(data).encode()))
        tmp.replace(path)
    return data['access_token']


def api(resource, params):
    if resource not in {'channels', 'playlistItems', 'videos', 'captions'}:
        raise ValueError('Ressource de lecture non autorisée')
    req = Request('https://www.googleapis.com/youtube/v3/' + resource + '?' + urlencode(params), headers={'Authorization': 'Bearer ' + access_token()})
    with urlopen(req, timeout=45) as r:
        return json.load(r)


def inventory():
    channels = api('channels', {'part': 'snippet,contentDetails', 'mine': 'true'})['items']
    matches = [c for c in channels if 'une minute pour comprendre' in c['snippet']['title'].casefold()]
    if len(matches) != 1:
        raise RuntimeError('Chaîne UMPC non identifiée de façon unique')
    channel = matches[0]
    ids, page = [], None
    while True:
        params = {'part': 'contentDetails', 'playlistId': channel['contentDetails']['relatedPlaylists']['uploads'], 'maxResults': 50}
        if page:
            params['pageToken'] = page
        result = api('playlistItems', params)
        ids.extend(i['contentDetails']['videoId'] for i in result['items'])
        page = result.get('nextPageToken')
        if not page:
            break
    videos = []
    for i in range(0, len(ids), 50):
        videos.extend(api('videos', {'part': 'snippet,status,contentDetails,fileDetails,processingDetails', 'id': ','.join(ids[i:i+50])})['items'])
    if len(videos) != len(set(ids)):
        raise RuntimeError('Inventaire YouTube incomplet : publication interrompue')
    return {'checked_at': datetime.now(timezone.utc).isoformat(), 'channel_id': channel['id'], 'videos': videos}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    data = inventory()
    out = ROOT / 'tmp/youtube/authenticated-inventory.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    for v in data['videos']:
        print(json.dumps({'id': v['id'], 'title': v['snippet']['title'], 'status': v['status']['privacyStatus'], 'publishAt': v['status'].get('publishAt'), 'publishedAt': v['snippet']['publishedAt'], 'file': v.get('fileDetails', {}).get('fileName'), 'embeddable': v['status'].get('embeddable')}, ensure_ascii=False))
    print(f"{len(data['videos'])} vidéos ; instantané privé enregistré hors public/ et hors Git.")
