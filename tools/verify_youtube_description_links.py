"""Audit final en lecture seule des liens et de la préservation des métadonnées YouTube."""
import hashlib
import argparse
import html
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from update_youtube_article_links import articles_by_id,transform,extract_urls,MUTABLE,CHANNEL,verify_scheduled_article
from youtube_readonly import inventory
from sync_youtube_articles import atomic_json

ROOT=Path(__file__).resolve().parent.parent
TRACK=ROOT/'tracking'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--include-scheduled',action='store_true')
    args=parser.parse_args()
    before_path=sorted(TRACK.glob('youtube-description-backup-*.private.json'))[0]
    before=json.loads(before_path.read_text(encoding='utf-8'))
    originals={v['id']:v for v in before['videos']}
    snap=inventory()
    if snap['channel_id']!=CHANNEL:raise RuntimeError('Chaîne différente')
    mapping=articles_by_id();rows=[];cache={}
    for v in snap['videos']:
        id=v['id'];old=originals[id];issues=[]
        for field in MUTABLE:
            if field!='description' and old['snippet'].get(field)!=v['snippet'].get(field):issues.append('Champ différent : '+field)
        expected_status=dict(old['status'])
        if expected_status.get('privacyStatus')=='private' and expected_status.get('publishAt') and v['status']['privacyStatus']=='public':
            expected_status['privacyStatus']='public'
            expected_status.pop('publishAt',None)
        if expected_status!=v['status']:issues.append('Statut ou programmation modifié hors publication prévue')
        scheduled=bool(args.include_scheduled and v['status']['privacyStatus']=='private' and v['status'].get('publishAt'))
        if scheduled:
            path,meta=mapping[id];url='https://uneminutepourcomprendre.fr/articles/'+meta['slug']+'/'
            expected,refs=transform(old['snippet']['description'],url)
            if v['snippet']['description']!=expected:issues.append('Description programmée différente du remplacement attendu')
            ok,reason=verify_scheduled_article(path,meta,v,refs)
            if not ok:issues.append(reason)
            state='Description préparée avant sortie, références dans le brouillon'
        elif v['status']['privacyStatus']!='public':
            if old['snippet']['description']!=v['snippet']['description']:issues.append('Description non publique modifiée')
            state='Différée, description conservée'
        else:
            path,meta=mapping[id];url='https://uneminutepourcomprendre.fr/articles/'+meta['slug']+'/'
            expected,refs=transform(old['snippet']['description'],url)
            if v['snippet']['description']!=expected:issues.append('Description différente du remplacement attendu')
            if url not in cache:
                with urlopen(Request(url,headers={'Cache-Control':'no-cache'}),timeout=30) as response:cache[url]=response.read()
            public=cache[url]
            local=(ROOT/'public/articles'/meta['slug']/'index.html').read_bytes()
            if hashlib.sha256(public).digest()!=hashlib.sha256(local).digest():issues.append('Page distante différente du build')
            text=public.decode('utf-8')
            for u in extract_urls('\n\n'.join(refs)):
                if html.escape(u,quote=True) not in text and u not in text:issues.append('Référence absente : '+u)
            state='Description et article vérifiés'
        rows.append({'id':id,'title':v['snippet']['title'],'privacy':v['status']['privacyStatus'],'state':state,'issues':issues})
    result={'checked_at':snap['checked_at'],'baseline':before_path.as_posix(),'rows':rows,'success':not any(r['issues'] for r in rows)}
    atomic_json(TRACK/'youtube-description-final-verification.private.json',result)
    print('Vidéos publiques vérifiées',sum(r['privacy']=='public' and not r['issues'] for r in rows))
    print('Descriptions programmées vérifiées',sum(r['state'].startswith('Description préparée') and not r['issues'] for r in rows))
    print('Autres vidéos non publiques conservées',sum(r['state']=='Différée, description conservée' and not r['issues'] for r in rows))
    for r in rows:
        if r['issues']:print('ÉCHEC',r['id'],r['issues'])
    raise SystemExit(0 if result['success'] else 1)


if __name__=='__main__':main()
