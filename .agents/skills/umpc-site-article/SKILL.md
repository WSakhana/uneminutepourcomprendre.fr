---
name: umpc-site-article
description: "Crée ou met à jour un article du site uneminutepourcomprendre.fr à partir d'une vidéo YouTube de la chaîne Une Minute Pour Comprendre et de son dossier de production (Documents, media, Scenes, Montage) : la vidéo intégrée en premier, un vrai texte éditorial structuré (pas une transcription), les images et schémas de la vidéo, et la bibliographie des sources réellement utilisées (auteur, publication, année, sujet, lien, publication originale en priorité). À utiliser dès que l'utilisateur donne une URL YouTube de la chaîne (youtu.be, youtube.com/watch) et/ou un dossier de production (D:\\@UMPC-Long\\Videos\\..., D:\\@UMPC-Shorts-Reactions\\Videos\\...) en demandant un article, une page article, « ajoute cette vidéo au site », « fais comme pour l'article 1 », ou pour corriger, compléter, réécrire un article existant (texte, sources, images, chapitres), même si le mot article n'est pas prononcé. Ne déploie pas et ne commit pas : utiliser umpc-site-deploy pour la mise en ligne."
---

# Article UMPC pour le site

Ce skill appartient au dépôt du site `uneminutepourcomprendre.fr` (HTML et CSS statiques, pages d'articles générées en
local). La racine du dépôt est à `../../..` de ce fichier ; vérifier qu'elle contient `public/` et
`tools/build_articles.py`, sinon s'arrêter et expliquer que le skill est réservé à ce dépôt. Lire `AGENTS.md` à la racine.

Pourquoi un article : la vidéo explique un mécanisme en quatre minutes ; l'article donne à ce même contenu une
vie dans les moteurs de recherche et sur les réseaux, avec plus de précision, les limites de ce qu'on sait et les
sources scientifiques. La vidéo reste toujours le premier élément de la page.

## Portée

- **Fait** : lit le dossier de production, rédige `content/articles/<slug>/article.toml` et `body.html`, construit les
  pages, contrôle le résultat, prépare un aperçu local.
- **Ne fait pas** : ne déploie pas sur OVH, ne commit pas, ne modifie pas le dossier de production (lecture seule), ne
  régénère aucune image ni vidéo. Ces étapes demandent une instruction explicite (`umpc-site-deploy` pour la mise en ligne).
- **Pas d'invention** : une date, un auteur, un chiffre ou une licence absents des documents se demandent ou se
  signalent comme à confirmer. Ils ne se devinent pas.

## Entrées à obtenir

1. L'**URL YouTube** de la vidéo (n'importe quelle forme : `youtu.be/ID?si=...`, `watch?v=ID`).
2. Le **dossier de production** (par exemple `D:\@UMPC-Long\Videos\3 - Les capacites etonnantes des bacteries`).
   S'il manque, le chercher d'abord dans `D:\@UMPC-Long\Videos\` et `D:\@UMPC-Shorts-Reactions\Videos\` d'après le titre,
   puis demander si le doute subsiste.
3. La **date de mise en ligne** de la vidéo, si l'utilisateur la connaît. Sinon la demander une fois ; à défaut,
   continuer avec la date du jour et le signaler clairement dans le compte rendu.

## Procédure

1. **Inventaire.** Exécuter, depuis la racine du dépôt :
   `py -3 .agents/skills/umpc-site-article/scripts/inspect_production.py --production "<dossier>" --youtube "<url>"`
   Il affiche l'identifiant YouTube, le titre réel (oEmbed, qui fait foi, apostrophes typographiques comprises), la
   **miniature réellement publiée**, les chapitres, la description, les sources citées, les affirmations vérifiées, la
   narration par scène, les droits des médias et les images candidates. Ajouter `--slug <slug>` pour imposer le slug
   (celui que l'utilisateur donne ; sinon celui proposé par le rapport, déduit du titre) et `--write-draft` pour créer un
   `article.toml` à compléter (les « TODO » empêchent le build tant qu'ils restent). Le brouillon est un point de
   départ : renommer les clés d'images si besoin, supprimer celles qui ne servent pas, renuméroter les sources.
2. **Lire le dossier en entier**, pas seulement le rapport : `Documents/Research.md`, `Script_Video.md`,
   `Narration.md`, `Social_Publishing.md` et `media/MediaSources.md`. Les formats varient d'un épisode à l'autre.
   Voir `references/editorial-guide.md` (matière première, plan, règles de rédaction).
3. **Choisir les images.** Médias réels avec leur licence d'abord, illustrations ensuite, schémas de la vidéo finale
   en dernier. Pour ces derniers, produire une planche contact
   (`scripts/contact_sheet.py --video <video finale> --start <s> --end <s> --step 3 --out <fichier hors dépôt>`) et la
   regarder avant de fixer `video_time` ; les positions des éléments sur la planche donnent directement les fractions de
   `box`. **Couverture : la miniature que le rapport désigne comme publiée**, pas la miniature « recommandée » de
   `Social_Publishing.md` (sur l'épisode 3, la recommandée n'est pas celle qui a été mise en ligne).
4. **Rédiger `article.toml` et `body.html`** selon `references/article-format.md` : une section par chapitre ou
   cas, un encadré « Ce qu'il ne faut pas en conclure » tiré des limites de la recherche, les figures, les boutons vers
   les chapitres. Chaque affirmation scientifique porte sa note `{{cite:Sn}}`. Écrire ces fichiers avec l'outil
   d'écriture de fichiers de l'agent, pas avec un heredoc shell : le texte est plein d'apostrophes qui font échouer
   les heredocs. La `description` (160 caractères au plus) est contrôlée par le build.
5. **Sources.** Seulement celles qui justifient la vidéo ; publication originale avant article secondaire ; métadonnées
   vérifiées par Europe PMC ou Crossref (voir le guide). Une source n'apparaît dans la bibliographie que si le texte la
   cite : le build le contrôle. Les ids `S1…` de `article.toml` sont propres à l'article (ordre d'affichage) et ne
   correspondent pas à ceux de `Research.md`.
6. **Construire et contrôler.**
   - `py -3 tools/build_articles.py` (génère les pages, les images, le sitemap, le bloc de l'accueil)
   - `py -3 tools/check_site.py` doit afficher « OK : aucun problème »
   - aperçu : `py -3 -m http.server 8000` depuis `public/`, puis ouvrir
     `http://localhost:8000/articles/<slug>/` et regarder à 375, 768 et 1280 px (vidéo en premier, aucun
     débordement horizontal, toutes les images chargées). Avec un outil de navigateur (Playwright), faire aussi défiler
     la page pour déclencher le chargement différé des images avant de les compter. Arrêter le serveur ensuite. Sans
     outil de navigateur, ne pas présenter l'aperçu comme fait : l'écrire dans le compte rendu.
7. **Compte rendu** : chemin des fichiers, titre, nombre de sources et d'images, et la liste de ce qui reste à
   confirmer par l'utilisateur (date de mise en ligne, sources lues en résumé seulement, choix de la couverture). Proposer
   la mise en ligne via `umpc-site-deploy`, sans la lancer. Terminer par le bloc à coller sur YouTube une fois l'article
   en ligne (le lien relie la vidéo à l'article et fait connaître le site ; ne rien publier soi-même) :
   ```text
   Description (en haut, avant les sources) :
   Article complet, schémas et sources : https://uneminutepourcomprendre.fr/articles/<slug>/

   Commentaire épinglé :
   L'article complet, avec les schémas et les publications scientifiques utilisées : https://uneminutepourcomprendre.fr/articles/<slug>/
   ```

## Mettre à jour un article existant

Modifier `article.toml` ou `body.html`, passer `modified` à la date du jour, relancer le build puis `check_site.py`.
Ne jamais éditer `public/articles/` à la main : ces fichiers sont réécrits à chaque build.

## Règles qui évitent les erreurs coûteuses

- Le texte public est en français, sans tiret cadratin, avec les nuances de la vidéo (« interprétation », « chez la
  souris », « non établi ») conservées ou renforcées, jamais gommées.
- Les noms scientifiques, absents de la voix, vont dans l'article.
- Une image tierce a toujours un auteur, une licence et un `credit_url`. Une image générée est marquée
  `generated = true` et jamais présentée comme une observation.
- Les consignes détaillées (sources, images, crédits, pièges) sont dans `references/editorial-guide.md`.
