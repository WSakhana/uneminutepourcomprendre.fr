"""Transfère les listes de références puis remplace celles de YouTube par l’article public.

--consolidate : complète les sources d’articles côté site uniquement.
Sans option : audit et propositions. --apply : descriptions seulement, après vérification
du HTML public. --include-scheduled autorise aussi les vidéos programmées après contrôle
des références dans leur brouillon. Outil manuel, jamais appelé par la tâche Windows.
"""
import argparse
import copy
import hashlib
import html
import json
import re
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from youtube_readonly import access_token, api, inventory
from sync_youtube_articles import atomic_json, lock, replace_scalar

ROOT=Path(__file__).resolve().parent.parent
TRACK=ROOT/'tracking'
SITE='https://uneminutepourcomprendre.fr'
CHANNEL='UCQjny8xBCjD1ilJqsXhTG-A'
MUTABLE=('title','description','tags','categoryId','defaultLanguage','defaultAudioLanguage')
HEADER=re.compile(r'^(?:#{1,3}\s*)?(?:sources?(?:\s+scientifiques)?|sources?\s+de\s+cet\s+épisode|cr[ée]dits?(?:\s+(?:images|m[ée]dias|des images))?|sources?\s+scientifiques\s+et\s+cr[ée]dits)\b',re.I)
MEDIA=re.compile(r'^(?:[-*]\s*)?(?:musique|cr[ée]dits|vid[ée]os?\s*(?:&|et)\s*m[ée]dias|autres\s+m[ée]dias|licences?)\s*[:(]',re.I)
URL_RE=re.compile(r'https?://[^\s<>]+')


def extract_urls(text):
    urls=[]
    for m in URL_RE.finditer(text):
        url=m[0].rstrip('.,;')
        while url.endswith(')') and url.count(')')>url.count('('):url=url[:-1]
        urls.append(url)
    return urls


def disclosure(line):
    return bool(re.search(r'(?i)(génér[ée].*(?:IA|intelligence artificielle)|illustrati(?:on|ves?).*(?:IA|génér))',line)) and not extract_urls(line)


def transform(description, article_url):
    """Conserve le texte, chapitres, hashtags et disclosures ; retire les listes de références."""
    blocks=re.split(r'\n\s*\n',description.replace('\r\n','\n').strip())
    kept,archives=[],[];in_refs=False
    for block in blocks:
        block=block.strip()
        if not block:continue
        urls=extract_urls(block)
        # Le lien final déjà installé n’est jamais archivé comme sa propre source.
        if all(u.startswith(SITE+'/articles/') for u in urls) and urls and (HEADER.match(block) or block==urls[0]):
            in_refs=False;continue
        is_header=bool(HEADER.match(block))
        is_list=bool(re.match(r'^[-*]\s+',block)) and (bool(urls) or in_refs)
        is_media=bool(MEDIA.match(block))
        if is_header or is_list or is_media:
            in_refs=True
            content=[];notes=[]
            for line in block.splitlines():
                if disclosure(line):notes.append(re.sub(r'^[-*]\s*','',line).strip())
                else:content.append(line)
            if content:archives.append('\n'.join(content))
            if notes:kept.append('\n'.join(notes))
        else:
            in_refs=False;kept.append(block)
    new='\n\n'.join(kept).strip()+'\n\nSources scientifiques et crédits :\n'+article_url
    if len(new)>5000:raise RuntimeError('Description supérieure à 5000 caractères')
    return new,archives


def linkify(line):
    parts=[];last=0
    for m in URL_RE.finditer(line):
        raw=m[0];url=extract_urls(raw)[0]
        parts.append(html.escape(line[last:m.start()]))
        parts.append('<a href="'+html.escape(url,quote=True)+'" target="_blank" rel="noopener noreferrer">'+html.escape(url)+'</a>')
        parts.append(html.escape(raw[len(url):]));last=m.end()
    parts.append(html.escape(line[last:]));return ''.join(parts)


def archive_section(video, archives):
    section_id='references-video-'+video['id']
    content=[]
    for block in archives:
        lines=block.splitlines()
        if len(lines)==1 and HEADER.match(lines[0]) and ':' in lines[0] and not lines[0].split(':',1)[1].strip():continue
        content.append('<p>'+'<br>\n'.join(linkify(line) for line in lines)+'</p>')
    return '<section id="'+section_id+'">\n<h2>Références et crédits de la vidéo</h2>\n<p>Références et attributions transférées depuis la description de « '+html.escape(video['snippet']['title'])+' », en complément des notes et crédits détaillés de cet article.</p>\n'+'\n'.join(content)+'\n</section>\n'


def articles_by_id():
    by_id={}
    for path in (ROOT/'content/articles').glob('*/article.toml'):
        meta=tomllib.loads(path.read_text(encoding='utf-8'))
        for v in [meta['video'],*meta.get('additional_videos',[])]:
            if v.get('id'):
                if v['id'] in by_id:raise RuntimeError('ID vidéo dans deux articles')
                by_id[v['id']]=(path,meta)
    return by_id


def get_video(id):
    items=api('videos',{'part':'snippet,status,contentDetails,localizations','id':id})['items']
    if len(items)!=1:raise RuntimeError('Vidéo non lisible : '+id)
    return items[0]


def verify_article(path, meta, video, archives):
    if meta.get('status','published')!='published' or video['status']['privacyStatus']!='public':
        return False,'Article ou vidéo pas encore public'
    url=SITE+'/articles/'+meta['slug']+'/'
    try:
        with urlopen(Request(url,headers={'Cache-Control':'no-cache'}),timeout=30) as r:
            public=r.read()
    except Exception:
        return False,'Article public inaccessible'
    local=ROOT/'public/articles'/meta['slug']/'index.html'
    if not local.exists() or hashlib.sha256(public).digest()!=hashlib.sha256(local.read_bytes()).digest():
        return False,'La page servie diffère du build local'
    text=public.decode('utf-8')
    if '/embed/'+video['id']+'?' not in text or 'id="sources"' not in text or 'id="credits"' not in text:
        return False,'Article non associé à la vidéo ou sections absentes'
    if archives and 'id="references-video-'+video['id']+'"' not in text:
        return False,'Les références actuelles ne sont pas encore transférées dans l’article'
    for u in extract_urls('\n\n'.join(archives)):
        if html.escape(u,quote=True) not in text and u not in text:
            return False,'Une URL de référence est absente de l’article'
    return True,'Article public et références présentes'


def verify_scheduled_article(path, meta, video, archives):
    """Contrôle local pour une correction manuelle avant la sortie d’une vidéo programmée."""
    status=video['status']
    if status.get('privacyStatus')!='private' or not status.get('publishAt'):
        return False,'Vidéo non programmée'
    if status.get('uploadStatus')!='processed' or status.get('embeddable') is not True:
        return False,'Vidéo non traitée ou non intégrable'
    ids=[v.get('id') for v in [meta.get('video',{}),*meta.get('additional_videos',[])]]
    if video['id'] not in ids or meta.get('status')!='draft' or not meta.get('ready'):
        return False,'Brouillon associé non prêt'
    body_path=path.with_name('body.html')
    if not body_path.is_file() or not meta.get('sources'):
        return False,'Texte ou sources scientifiques absents'
    body=body_path.read_text(encoding='utf-8')
    if archives and 'id="references-video-'+video['id']+'"' not in body:
        return False,'Références non transférées dans le brouillon'
    for u in extract_urls('\n\n'.join(archives)):
        if u not in body and html.escape(u,quote=True) not in body:
            return False,'Une URL de référence est absente du brouillon'
    return True,'Lien préparé avant publication ; références conservées dans le brouillon'


def update_description(video,new_description):
    snippet={k:copy.deepcopy(video['snippet'][k]) for k in MUTABLE if k in video['snippet']}
    snippet['description']=new_description
    body=json.dumps({'id':video['id'],'snippet':snippet},ensure_ascii=False).encode('utf-8')
    req=Request('https://www.googleapis.com/youtube/v3/videos?part=snippet',data=body,method='PUT',headers={'Authorization':'Bearer '+access_token(),'Content-Type':'application/json; charset=utf-8'})
    with urlopen(req,timeout=45) as r:response=json.load(r)
    if response['snippet']['description']!=new_description:raise RuntimeError('Réponse de mise à jour différente du texte envoyé')
    # YouTube peut encore renvoyer brièvement l’ancienne description après le PUT réussi.
    for delay in (0,0.75,1.5,3):
        if delay:time.sleep(delay)
        after=get_video(video['id'])
        if after['snippet']['description']==new_description:break
    if after['snippet']['description']!=new_description:raise RuntimeError('Description non conforme après lecture : '+video['id'])
    for k in MUTABLE:
        if k!='description' and video['snippet'].get(k)!=after['snippet'].get(k):raise RuntimeError('Métadonnée modifiée : '+k)
    if video['status']!=after['status']:raise RuntimeError('Statut changé pendant la mise à jour : '+video['id'])
    if video.get('contentDetails')!=after.get('contentDetails'):raise RuntimeError('Détails vidéo changés : '+video['id'])
    for lang,loc in video.get('localizations',{}).items():
        if loc['title']!=after.get('localizations',{}).get(lang,{}).get('title'):raise RuntimeError('Titre localisé changé')
    old={k:(v['url'].split('?')[0],v.get('width'),v.get('height')) for k,v in video['snippet'].get('thumbnails',{}).items()}
    now={k:(v['url'].split('?')[0],v.get('width'),v.get('height')) for k,v in after['snippet'].get('thumbnails',{}).items()}
    if old!=now:raise RuntimeError('Miniatures modifiées')
    return after


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--consolidate',action='store_true');parser.add_argument('--apply',action='store_true')
    parser.add_argument('--include-scheduled',action='store_true',help='correction manuelle des descriptions programmées, avec leur futur lien d’article')
    args=parser.parse_args()
    with lock():
        snap=inventory()
        if snap['channel_id']!=CHANNEL:raise RuntimeError('Chaîne authentifiée différente')
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        existing_backups=sorted(TRACK.glob('youtube-description-backup-*.private.json'))
        backup=existing_backups[0] if existing_backups else TRACK/('youtube-description-backup-'+stamp+'.private.json')
        # Le premier instantané est conservé ; les sauvegardes suivantes concernent les écritures réelles.
        if not existing_backups:atomic_json(backup,snap)
        mapping=articles_by_id();rows=[]
        for v in snap['videos']:
            id=v['id']
            if id not in mapping:
                rows.append({'id':id,'title':v['snippet']['title'],'state':'Sans article associé'});continue
            path,meta=mapping[id];url=SITE+'/articles/'+meta['slug']+'/'
            new,archives=transform(v['snippet']['description'],url)
            row={'id':id,'title':v['snippet']['title'],'article_url':url,'privacy':v['status']['privacyStatus'],'before':v['snippet']['description'],'proposed':new,'references':archives,'state':'Préparée'}
            if args.consolidate and archives:
                body_path=path.with_name('body.html');body=body_path.read_text(encoding='utf-8')
                section=archive_section(v,archives);sid='references-video-'+id
                pattern=r'<section id="'+re.escape(sid)+r'">.*?</section>\s*'
                updated=re.sub(pattern,lambda _:section,body,flags=re.S) if 'id="'+sid+'"' in body else body.rstrip()+'\n\n'+section
                if body!=updated:
                    body_path.write_text(updated,encoding='utf-8')
                    path.write_text(replace_scalar(path.read_text(encoding='utf-8'),'modified',datetime.now(ZoneInfo('Europe/Paris')).strftime('%Y-%m-%d')),encoding='utf-8')
                    row['state']='Article complété localement'
            if not args.consolidate:
                if v['snippet']['description']==new and v['status']['privacyStatus']=='public' and meta.get('status','published')=='published':
                    row['state']='Déjà conforme';rows.append(row);print(row['state'],id,meta['slug'],flush=True);continue
                current=get_video(id) if args.apply else v
                new,archives=transform(current['snippet']['description'],url)
                row.update(before=current['snippet']['description'],proposed=new,references=archives)
                scheduled=bool(args.include_scheduled and current['status'].get('privacyStatus')=='private' and current['status'].get('publishAt'))
                ok,reason=verify_scheduled_article(path,meta,current,archives) if scheduled else verify_article(path,meta,current,archives)
                row['reason']=reason
                row['scheduled_at']=current['status'].get('publishAt')
                row['article_status']=meta.get('status','published')
                if not ok:row['state']='Différée'
                elif current['snippet']['description']==new:row['state']='Déjà conforme'
                elif args.apply:
                    # Une sauvegarde fraîche par vidéo couvre les changements survenus après l’inventaire.
                    atomic_json(TRACK/('youtube-description-'+id+'-'+stamp+'.private.json'),{'before':current,'new_description':new,'article_url':url})
                    after=update_description(current,new)
                    row['after']=after['snippet']['description'];row['state']='Modifiée et relue'
                    atomic_json(TRACK/'youtube-article-links-progress.private.json',{'checked_at':snap['checked_at'],'completed':rows+[row]})
                else:row['state']='Prête'
            rows.append(row);print(row['state'],id,meta['slug'],flush=True)
        result={'checked_at':snap['checked_at'],'backup':backup.as_posix(),'mode':'apply' if args.apply else 'consolidate' if args.consolidate else 'audit','include_scheduled':args.include_scheduled,'rows':rows}
        atomic_json(TRACK/'youtube-article-links.private.json',result)
        lines=['# Liens articles dans les descriptions YouTube','', 'Contrôle : '+snap['checked_at']+'.', '', '| Vidéo | Article | État |', '|---|---|---|']
        for r in rows:lines.append('| ['+r['title'].replace('|','/')+'](https://youtu.be/'+r['id']+') | '+('[Article]('+r['article_url']+')' if r.get('article_url') else '')+' | '+r['state']+' |')
        (TRACK/'YouTube_Liens_Articles.private.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        print('Traitement terminé :',len(rows),'vidéos.')


if __name__=='__main__':main()
