# Site uneminutepourcomprendre.fr

Site officiel de la chaîne **Une Minute Pour Comprendre** : une page d'accueil et une section Articles. Statique : HTML et
CSS, pas de framework, pas de backend. Les pages d'articles sont générées en local, puis `public/` est envoyé tel quel sur
l'hébergement OVH. Lire `README.md` pour la structure, l'aperçu local et les commandes.

## Skills du projet (`.agents/skills/`)

- **`umpc-site-article`** : crée ou met à jour l'article d'une vidéo à partir de son URL YouTube et de son dossier de
  production (`D:\@UMPC-Long\Videos\...` ou `D:\@UMPC-Shorts-Reactions\Videos\...`). Ne déploie pas.
- **`umpc-site-deploy`** : build, contrôles, envoi SFTP sur OVH, vérification du site en ligne.

Codex lit `.agents/skills/` directement. Claude Code lit `.claude/skills/`, qui est une **jonction locale** vers
`.agents/skills/` (non versionnée) : la recréer après un clonage avec `powershell -ExecutionPolicy Bypass -File tools/link_skills.ps1`
(sous Linux ou macOS : `mkdir -p .claude && ln -s ../.agents/skills .claude/skills`).

## Commandes

```powershell
py -3 tools/build_articles.py          # régénère articles, accueil, 404, sitemap (--images pour refaire les images)
py -3 tools/check_site.py              # contrôle statique de public/ (liens, ancres, ids, alt, descriptions)
cd public; py -3 -m http.server 8000   # aperçu local ; les URL propres ne marchent pas en file://
py -3 tools/deploy_sftp.py --dry-run   # simulation ; sans option : envoi de public/ dans www/
py -3 tools/verify_live.py             # vérifie le site en ligne après un déploiement
py -3 tools/indexnow.py                # signale les URL du sitemap à IndexNow (Bing...) après un déploiement
```

## Règles

- Ne jamais modifier à la main `public/articles/`, `public/404.html`, `public/sitemap.xml` ni le bloc entre
  `<!-- articles:start -->` et `<!-- articles:end -->` de `public/index.html` : le build les réécrit. Les sources d'un
  article sont `content/articles/<slug>/article.toml` et `body.html`.
- Après toute modification de `public/assets/css/style.css` ou `public/assets/js/`, relancer le build : les liens portent
  une empreinte `?v=...` qui renouvelle le cache d'un mois.
- Identité visuelle et responsive existants à conserver (couleurs en variables CSS en tête de `style.css`, points de
  rupture 640, 768 et 960 px). Même largeur de contenu sur tout le site (`.container`, 1180 px).
- Le dossier de production d'une vidéo est en **lecture seule** ; on n'y écrit rien depuis ce dépôt.
- Livrables publics en français, sans tiret cadratin. Affirmations scientifiques rattachées à des sources fiables, avec
  leurs limites ; publication originale de préférence à un article secondaire ; jamais de source ajoutée « pour faire
  nombre ».
- Déployer, commiter ou pousser seulement sur demande explicite. Le dépôt est **public** sur GitHub : l'hôte, l'utilisateur
  et le mot de passe SFTP viennent des variables d'environnement `UMPC_SFTP_HOST`, `UMPC_SFTP_USER` et
  `UMPC_SFTP_PASSWORD` ; ne jamais les demander dans une conversation, les afficher ni les écrire dans un fichier.
- Ne jamais activer GitHub Pages sur ce dépôt : une copie de `public/` sur `github.io` dupliquerait le contenu du site.
- Sortie de console en UTF-8 : les outils de `tools/` configurent leur sortie ; sous PowerShell, préférer `py -3`.
