"""Compare les pages réellement servies aux pages locales et refuse l’accès aux brouillons."""
import concurrent.futures
import hashlib
import sys
import tomllib
import urllib.error
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent.parent
SITE='https://uneminutepourcomprendre.fr'


def check(meta):
    slug=meta['slug'];path=f'/articles/{slug}/'
    expected=200 if meta.get('status','published')=='published' else 404
    try:
        with urlopen(Request(SITE+path,headers={'User-Agent':'UMPC-publication-verification/1.0','Cache-Control':'no-cache'}),timeout=30) as r:
            status=r.status;data=r.read()
    except urllib.error.HTTPError as e:
        status=e.code;data=e.read()
    except Exception as e:
        return slug,False,type(e).__name__
    if status!=expected:return slug,False,f'HTTP {status}, attendu {expected}'
    if expected==200:
        local=(ROOT/'public/articles'/slug/'index.html').read_bytes()
        if hashlib.sha256(data).digest()!=hashlib.sha256(local).digest():
            return slug,False,'HTML distant différent de la version locale'
    return slug,True,str(status)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    metas=[tomllib.loads(p.read_text(encoding='utf-8')) for p in (ROOT/'content/articles').glob('*/article.toml')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(check,metas))
    for slug,ok,detail in results:
        if not ok:print('ÉCHEC',slug,detail)
    print(f'{sum(ok for _,ok,_ in results)}/{len(results)} pages conformes : HTML publié identique et brouillons en 404.')
    raise SystemExit(0 if all(ok for _,ok,_ in results) else 1)


if __name__=='__main__':main()
