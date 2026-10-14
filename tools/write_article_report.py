"""Exporte le suivi lisible et les descriptions proposées ; aucun fichier n’est publié."""
import json
import sys
import tomllib
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TRACK = ROOT/'tracking'
PARIS = ZoneInfo('Europe/Paris')


def local_date(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(PARIS).strftime('%d/%m/%Y à %H:%M') if value else ''


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    data = json.loads((TRACK/'articles.private.json').read_text(encoding='utf-8'))
    records = data['records']
    links_path=TRACK/'youtube-article-links.private.json'
    links=json.loads(links_path.read_text(encoding='utf-8')) if links_path.exists() else {}
    linked=sum(r.get('state') in ('Modifiée et relue','Déjà conforme') for r in links.get('rows',[]))
    existing = {'animaux-squelettes-etonnants', 'apophis-2029-plus-pres-que-nos-satellites', 'capacites-surprenantes-des-bacteries', 'comment-moustique-tigre-passe-hiver', 'pourquoi-piqure-tique-indolore'}
    titles = {p.parent.name: tomllib.loads(p.read_text(encoding='utf-8'))['short_title'] for p in (ROOT/'content/articles').glob('*/article.toml')}
    groups = [
        ('Articles publiés et vérifiés', [r for r in records if r['article_status']=='published']),
        ('Vidéos programmées : articles gardés en brouillon', [r for r in records if any(v['scheduled_at'] for v in r['youtube'])]),
        ('Projets sans ID YouTube confirmé', [r for r in records if not r['youtube_ids']]),
        ('Vidéo non répertoriée', [r for r in records if any(v['privacy']=='unlisted' for v in r['youtube'])]),
    ]
    counts=Counter(r['article_status'] for r in records)
    lines=['# Suivi des articles UMPC', '', 'Instantané : '+local_date(data['checked_at'])+' (Europe/Paris).', '',
        f"{len(records)} articles : {counts['published']} publiés et {counts['draft']} brouillons. {len(existing)} pages existantes mises à jour, {len(records)-len(existing)} nouveaux articles ou brouillons.", '',
        'Le JSON `articles.private.json` est la source de suivi. Les brouillons n’ont aucune page publique : leurs URL ci-dessous sont réservées pour leur publication future.', '',
        (f'{linked} descriptions YouTube ont leur lien d’article contrôlé. Les vidéos programmées peuvent avoir leur lien réservé avant la sortie, avec leurs références conservées dans le brouillon. Les modifications de descriptions sont exclusivement manuelles, sur demande.' if linked else 'Les descriptions YouTube sont préparées. Leur modification est exclusivement manuelle, sur demande.'), '',
        '## Automatisation', '',
        'La tâche Windows « UMPC - Synchronisation articles YouTube » vérifie les statuts toutes les quinze minutes et à la connexion utilisateur, sans Codex ouvert. Le PC doit être allumé, connecté, avec une session utilisateur ouverte et le lecteur Google Drive disponible.', '',
        'Une date prévue ne publie jamais à elle seule. Seules les vidéos traitées, réellement publiques et intégrables rendent un article prêt éligible. Les changements de date sont relus. Les IDs sont uniques, les exécutions ne se chevauchent pas et les envois inchangés sont évités.', '',
        'La tâche Windows ne modifie jamais YouTube. Elle gère uniquement la publication des articles et le suivi.', '',
        '## Vérifications et limites', '',
        '- Contrôles initiaux du 13 octobre 2026 : build et contrôle statique réussis ; 12 tests de publication et de compatibilité réussis. Le build et le contrôle statique sont repris par chaque synchronisation de publication.',
        '- Contrôle navigateur initial du 13 octobre 2026 : 117 mesures sur 39 pages, à 375, 768 et 1280 px. Aucun débordement, vidéos avant le titre et figures limitées en hauteur. Les publications ultérieures réutilisent ces gabarits ; elles ne constituent pas une nouvelle inspection visuelle automatique.',
        '- API YouTube : visibilité, traitement et intégration des vidéos contrôlés. Lecture du Short IceCube testée jusqu’au terme sans erreur dans le navigateur.',
        '- 65 exports analysés avec FFprobe, 42 timelines inspectées et planches de quatre images par export examinées. Cette inspection n’est pas une écoute intégrale de tous les films.',
        '- Les métadonnées des DOI ont été contrôlées auprès de Crossref. Les recherches et leurs limites ont été exploitées ; toutes les publications n’étaient pas disponibles en texte intégral.',
        '- Les médias tiers repris sur le site ont des attributions et des licences documentées. Les reconstitutions et images de synthèse sont signalées.',
        '- Plusieurs dossiers ne documentent pas intégralement la provenance ou les conditions de licence de la musique et des effets. Aucun droit audio n’a été déclaré acquis ; les pages et le suivi indiquent ces lacunes.',
        '- La vidéo de bienvenue est non répertoriée et sans dossier de production retrouvé. Le brouillon reste bloqué.',
        '',
        'Le déploiement initial du 13 octobre a envoyé 299 fichiers sur OVH. Le contrôle public a confirmé le HTML identique pour les articles publiés et les 404 pour les brouillons. IndexNow a accepté le signalement. Les derniers états se trouvent dans `sync-state.local.json`. Aucun commit ni push n’a été effectué par cette mission.', '']
    for heading, rows in groups:
        if not rows:
            continue
        lines += ['## '+heading, '', '| Projet | Vidéo YouTube | Date YouTube | Article | Travail |', '|---|---|---|---|---|']
        for r in sorted(rows,key=lambda r: next((v['scheduled_at'] for v in r['youtube'] if v['scheduled_at']),r['slug'])):
            vids=', '.join('[`'+id+'`](https://youtu.be/'+id+')' for id in r['youtube_ids']) or 'Aucun ID confirmé'
            dates=' ; '.join(local_date(v['scheduled_at'] or v['published_at']) for v in r['youtube'] if v['scheduled_at'] or v['published_at'])
            keys=', '.join(filter(None,r.get('project_keys',[])))
            work='Mise à jour' if r['slug'] in existing else 'Création'
            lines.append(f"| {keys} | {vids} | {dates or 'Non publiée'} | [{titles[r['slug']]}]({r['article_url']}) | {work} |")
        lines.append('')
    lines += ['## Sources et crédits restant à compléter', '', '| Article | État des sources | État des crédits |', '|---|---|---|']
    for r in records:
        if 'partiels' in r['credits_status'] or not r['ready']:
            lines.append('| '+titles[r['slug']]+' | '+r['sources_status'].replace('|','/')+' | '+r['credits_status'].replace('|','/')+' |')
    (TRACK/'Suivi_Articles_UMPC.private.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    desc=['# Descriptions YouTube proposées', '', 'Instantané : '+local_date(data['checked_at'])+f'. Liens d’articles contrôlés dans {linked} descriptions YouTube. Les textes ci-dessous restent des propositions éditoriales ; le remplacement des sources conserve le texte actuel.', '',
        'Les descriptions des vidéos programmées peuvent contenir leur futur lien d’article avant la sortie, sur demande manuelle. L’article reste en brouillon jusqu’à la publication réelle de la vidéo. Les crédits incomplets restent signalés dans le suivi et dans les pages. La disponibilité d’une proposition ne vaut pas confirmation de tous les droits du film.', '']
    for r in records:
        desc += ['## '+titles[r['slug']], '', 'Projet : '+', '.join(filter(None,r.get('project_keys',[])))+'. IDs : '+', '.join(r['youtube_ids'])+'.', '',
            'Article : '+r['article_status']+'. Publication en ligne vérifiée : '+(local_date(r['publication_verified_at']) or 'non')+'.', '',
            'Crédits : '+r['credits_status']+'.', '', '```text', r['youtube_description'], '```', '']
    (TRACK/'Descriptions_YouTube.private.md').write_text('\n'.join(desc)+'\n',encoding='utf-8')
    print(f'{len(records)} articles et descriptions exportés dans tracking/.')


if __name__=='__main__':main()
