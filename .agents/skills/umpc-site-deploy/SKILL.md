---
name: umpc-site-deploy
description: "Met en ligne le site uneminutepourcomprendre.fr sur l'hébergement OVH (SFTP, dossier www/) avec contrôles avant et après : régénération des pages d'articles, vérification statique de public/, simulation, envoi, puis vérification du site en ligne (statuts, redirections, page 404, ressources, canonical). À utiliser dès que l'utilisateur demande de publier, déployer, mettre en ligne, envoyer sur OVH ou pousser le site (« publish OVH », « deploy », « mets l'article en ligne »), ou de vérifier que la version en ligne est conforme, même sans citer OVH. Le mot de passe SFTP vient uniquement de la variable d'environnement UMPC_SFTP_PASSWORD : ne jamais le demander dans la conversation ni l'écrire quelque part."
---

# Déploiement OVH du site UMPC

Ce skill appartient au dépôt du site `uneminutepourcomprendre.fr`. La racine du dépôt est à `../../..` de ce fichier ;
vérifier qu'elle contient `public/` et `tools/deploy_sftp.py`, sinon s'arrêter. Lire `AGENTS.md` à la racine.

Pourquoi tant de contrôles : un déploiement écrase les fichiers du site public, et le script ne supprime jamais rien sur le
serveur. Une page cassée ou un lien mort mis en ligne se voit tout de suite et se corrige mal ; les contrôles locaux
sont gratuits, ceux d'après déploiement prouvent que le serveur sert bien ce qu'on y a envoyé.

## Portée et autorisation

- Une demande explicite de publier ou de déployer vaut autorisation d'envoyer `public/` sur `www/`. Une simple demande de
  « vérifier » ou de « préparer » n'envoie rien : s'arrêter après la simulation.
- Le skill ne commit pas et ne pousse pas de code : il signale seulement l'état de git (voir l'étape 1).
- Il ne supprime aucun fichier distant. Une page renommée ou retirée reste en ligne tant qu'elle n'est pas supprimée à la
  main (client SFTP) ; le signaler à l'utilisateur et ne rien supprimer sans son accord explicite.

## Procédure

1. **État du dépôt.** `git status --short`. S'il y a des modifications non commitées dans `public/`, `content/` ou
   `tools/`, le dire : l'envoi reflète le disque, pas le dernier commit. Proposer de commiter d'abord (ne pas le faire
   sans demande). Si la demande de déployer est claire, continuer.
2. **Pages à jour.** `py -3 tools/build_articles.py`, puis `git status --short public`. Si des fichiers de `public/` ont
   changé, c'est que les pages n'étaient pas à jour avec `content/` : le signaler (ils partent en ligne dans leur
   version fraîche). Une erreur du build (« TODO », source non citée...) interrompt le déploiement : la corriger d'abord.
3. **Contrôle statique.** `py -3 tools/check_site.py` doit afficher « OK : aucun problème » (liens locaux, ancres, ids,
   h1, alt, descriptions de 160 caractères au plus, sitemap). Sinon, corriger ou s'arrêter.
4. **Prérequis d'envoi.**
   - `paramiko` : `py -3 -c "import paramiko"` ; s'il manque, `py -3 -m pip install paramiko`.
   - Hôte et utilisateur : `UMPC_SFTP_HOST` et `UMPC_SFTP_USER` doivent être définies. Tester leur présence sans les
     afficher : `[ -n "$UMPC_SFTP_HOST" ] && [ -n "$UMPC_SFTP_USER" ] && echo définies || echo absentes` (Bash) ou
     `$env:UMPC_SFTP_HOST -and $env:UMPC_SFTP_USER` (PowerShell). Si l'une manque, ne pas la demander dans la
     conversation : indiquer à l'utilisateur de la définir une fois (`setx UMPC_SFTP_HOST "..."`, `setx UMPC_SFTP_USER "..."`,
     valeurs dans l'espace client OVH, puis nouveau terminal), et s'arrêter. Ces valeurs ne sont jamais écrites dans le
     dépôt, qui est public.
   - Mot de passe : tester seulement la présence de la variable, sans l'afficher :
     `[ -n "$UMPC_SFTP_PASSWORD" ] && echo définie || echo absente` (Bash) ou `$null -ne $env:UMPC_SFTP_PASSWORD`
     (PowerShell). Si elle est absente, ne pas demander le mot de passe dans la conversation : donner à l'utilisateur la
     commande pour la définir dans son terminal (`$env:UMPC_SFTP_PASSWORD = "..."`, valable pour la session) ou pour lancer
     lui-même `py -3 tools/deploy_sftp.py` (le script demande le mot de passe au clavier), puis s'arrêter.
5. **Simulation.** `py -3 tools/deploy_sftp.py --dry-run` liste les fichiers locaux à envoyer, sans connexion.
6. **Envoi.** `py -3 tools/deploy_sftp.py` envoie `public/` dans `www/` (hôte et utilisateur lus dans
   `UMPC_SFTP_HOST` et `UMPC_SFTP_USER`). Lire la fin de la sortie : « N fichiers envoyés ». En cas d'échec d'authentification, ne pas
   réessayer en boucle (OVH peut bloquer l'adresse après plusieurs échecs) : un seul nouvel essai au plus, puis rendre la
   main à l'utilisateur.
7. **Vérification en ligne.** `py -3 tools/verify_live.py` (ajouter `--base <url>` pour un autre domaine). Il contrôle le
   200 de chaque URL du sitemap, les redirections `http` vers `https`, `www` vers le domaine nu et `index.html` vers
   l'URL propre, la page 404 personnalisée, toutes les ressources des pages et les en-têtes de sécurité. En cas d'échec,
   le rapporter tel quel avec la liste des contrôles en échec ; ne pas conclure que « ça marche ».
8. **Notifier les moteurs.** Seulement si la vérification en ligne est conforme : `py -3 tools/indexnow.py` signale les
   URL du sitemap à IndexNow (Bing, Yandex, Seznam, Naver ; pas Google). Un statut 200 ou 202 est un succès ; un 403
   signifie que le fichier de clé n'est pas encore servi (vérifier qu'il a été envoyé). Un échec ici ne remet pas en
   cause le déploiement : le signaler.
9. **Compte rendu.** Nombre de fichiers envoyés, résultat de la vérification, et ce qui reste à faire par l'utilisateur :
   - Search Console : soumettre `https://uneminutepourcomprendre.fr/sitemap.xml` et demander l'indexation de la nouvelle page ;
   - tester l'aperçu de partage (débogueur Facebook) et le test des résultats enrichis de Google sur la nouvelle URL.

## Si quelque chose tourne mal

- **Retour en arrière** : revenir au commit précédent (`git checkout <commit> -- public content tools`), relancer le build
  et le déploiement. Comme rien n'est supprimé en ligne, un retour restaure les fichiers écrasés ; demander avant
  d'exécuter une commande git qui modifie l'arbre de travail.
- **Page 404 du site non servie** : vérifier que `public/.htaccess` (qui déclare `ErrorDocument 404 /404.html`) a bien été
  envoyé et qu'il n'a pas été modifié sur le serveur.
- **Ancien CSS ou JS affiché** : les pages portent une empreinte (`?v=...`) ; si elle n'a pas changé, c'est que le build
  n'a pas été relancé après la modification.
- **Mise en cache** : le HTML n'est pas mis en cache (expiration immédiate), les images et le CSS le sont longtemps.

## Ce qu'on n'écrit jamais

Le mot de passe SFTP n'est ni affiché, ni journalisé, ni écrit dans un fichier, une commande visible ou un commit. Le
dépôt est public : l'hôte et l'utilisateur SFTP n'y sont pas écrits non plus. Le
dépôt ignore déjà `.env`, `*.key` et `*.pem` : ne pas y créer de fichier d'identifiants.
