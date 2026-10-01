@AGENTS.md

# Claude dans le site UMPC

Les skills `umpc-site-article` et `umpc-site-deploy` sont chargés depuis `.claude/skills/` (jonction vers
`.agents/skills/`, voir `AGENTS.md`). Si Claude ne les voit pas, lancer `powershell -ExecutionPolicy Bypass -File tools/link_skills.ps1`.

Pour créer un article, utiliser `umpc-site-article` dès que l'utilisateur donne une URL YouTube de la chaîne ou un dossier
de production ; pour mettre en ligne, `umpc-site-deploy`. Pour vérifier le rendu d'une page, un navigateur piloté
(Playwright) est utile : charger la page via `http://localhost:8000`, mesurer le débordement horizontal à 375, 768 et
1280 px et faire défiler la page avant de compter les images (chargement différé).
