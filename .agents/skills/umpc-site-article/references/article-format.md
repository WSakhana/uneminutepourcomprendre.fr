# Format d'un article (`content/articles/<slug>/`)

Un article = deux fichiers lus par `tools/build_articles.py`. Le dossier porte le slug, qui devient l'URL
`/articles/<slug>/`. S'il existe, `content/articles/capacites-surprenantes-des-bacteries/` est un exemple complet ; sinon
les extraits ci-dessous suffisent.

## `article.toml`

Champs obligatoires (le build s'arrête avec un message clair s'il en manque, ou s'il reste un « TODO ») :

| Champ | Contenu |
|---|---|
| `slug` | identique au nom du dossier ; minuscules, chiffres, tirets, sans accent |
| `title` | titre de la vidéo YouTube, à l'identique |
| `short_title` | 4 à 6 mots, pour le fil d'Ariane |
| `category` | `"Science"`, `"Animaux"`, `"Corps humain"` ou `"Nature"` (les quatre univers de la chaîne) |
| `description` | meta description, **160 caractères au maximum** (`tools/check_site.py` le vérifie) |
| `lead` | chapô : pose la question de la vidéo en 2 ou 3 phrases |
| `published`, `modified` | dates ISO `AAAA-MM-JJ` ; `published` = date réelle de mise en ligne de la vidéo (la demander) |
| `cover` | clé d'une image de `[images.*]` : sert de vignette de carte et d'image de partage 1200 x 630 |
| `production` | chemin du dossier de production (barres obliques `/`) |
| `video_file` | vidéo finale relative à `production`, requise si une image utilise `video_time` |
| `keywords` | recommandé : liste de 5 à 8 mots-clés (sujet, noms scientifiques) ; alimente les données structurées et les balises `article:tag` |
| `method` | facultatif : note « À propos de cet article » (accès aux sources, illustrations) |

```toml
[video]
id = "PwoQaj9kHKQ"           # identifiant YouTube
title = "..."
duration_seconds = 235.5     # ffprobe de la vidéo finale
upload_date = "2026-10-01"

[[chapters]]                 # chapitres de la description YouTube, en secondes
t = 0
label = "Une bactérie transforme de l'or dissous"
```

### Images

```toml
[images.cle_courte]          # snake_case, utilisée dans body.html : {{figure:cle_courte}}
src = "media/images/fichier.jpg"     # relatif à production ; OU :
# video_time = 153                    # image extraite de la vidéo finale (secondes)
# box = [0.05, 0.28, 0.95, 0.72]      # recadrage facultatif en fractions x0, y0, x1, y1
alt = "Description visuelle factuelle (lecteurs d'écran)"
caption = "Légende qui apprend quelque chose, avec la limite si besoin"
credit = "Auteur, licence · recadrée"            # affiché sous la légende
credit_url = "https://commons.wikimedia.org/wiki/File:..."   # lien de la fiche source (obligatoire pour une image tierce)
generated = true             # illustration générée ou schéma de la vidéo : badge « Illustration »
```

Le générateur écrit `public/assets/img/articles/<slug>/<cle>-640.webp` et `-1280.webp` (pas d'agrandissement : une
source étroite n'a qu'une version), ajoute `srcset`, `width`, `height` et le chargement différé. Une image
plus haute que large est affichée en colonne étroite. Les images avec `credit_url` alimentent automatiquement la section
« Crédits des images ».

### Sources

```toml
[[sources]]
id = "S1"                    # S1, S2... dans l'ordre d'affichage : le numéro affiché [n] est la position
authors = "Wiesemann N. et al."      # premier auteur + « et al. » tant que les co-auteurs ne sont pas vérifiés
title = "Titre exact de la publication"
publication = "Journal of Bacteriology"   # + volume et pages si connus
year = "2013"
topic = "Ce que la source justifie dans la vidéo"
url = "https://doi.org/10.xxxx/xxxx"      # DOI de l'éditeur de préférence
kind = "Étude originale"     # « Présentation institutionnelle de la source 3 », « Contexte »...
```

## `body.html`

HTML brut, une `<section id="...">` par partie (le sommaire est généré à partir de ces sections). Marqueurs remplacés par
le générateur :

| Marqueur | Résultat |
|---|---|
| `{{figure:cle}}` | `<figure>` avec image, légende, badge « Illustration » et crédit |
| `{{cite:S1}}` | appel de note `[1]` vers la source |
| `{{chapitre:73}}` | bouton « Voir ce passage dans la vidéo (01:13) » ; la valeur doit être le `t` d'un chapitre |

Le build refuse : une image, une source ou un chapitre inconnus ; une source listée mais jamais citée ; un `TODO`.

Structure d'une section de contenu (classes déjà stylées dans `public/assets/css/style.css`) :

```html
<section id="or">
<h2><span class="cas-num" aria-hidden="true">1</span>Titre de la partie</h2>
{{figure:or_illustration}}
<p>Paragraphe avec une note.{{cite:S1}}</p>
<aside class="callout">                         <!-- callout--alert (bord rouge) pour une limite majeure -->
<h3>Ce qu'il ne faut pas en conclure</h3>
<ul>
<li>Limite 1 avec <strong>le mot clé en gras</strong>.</li>
</ul>
</aside>
<p class="watch">{{chapitre:0}}</p>
</section>
```

Sections habituelles : `en-bref` (liste `<ul class="key-points">` : une phrase par cas, réponse d'abord, avec ses
notes et sa limite principale), `intro` (avec son `<h2>`, sans numéro), une section numérotée par cas ou par chapitre,
`conclusion`, `faq` (`<h2>Questions fréquentes</h2>`, puis 4 à 6 `<h3>` formulés comme une vraie question de recherche
suivis d'un `<p>` de 2 à 3 phrases). « En bref » et la FAQ ne contiennent que ce que le corps du texte et ses sources
établissent, avec les mêmes notes `{{cite:Sn}}` et les mêmes limites : ce sont les passages que les moteurs de réponse IA
reprennent le plus volontiers. Plusieurs notes à la suite sont permises (`{{cite:S2}}{{cite:S3}}`). Les boutons
« copier le lien » des titres et des sources, le sommaire, la liste des sources, les crédits, le bloc d'abonnement,
les chapitres et les données structurées (Article, VideoObject, fil d'Ariane) sont ajoutés par le générateur : ne pas les
écrire à la main.

## Ce que le build produit

`py -3 tools/build_articles.py` réécrit `public/articles/index.html`, `public/articles/<slug>/index.html`, les images,
`public/404.html`, `public/sitemap.xml` (avec les images des articles), `public/feed.xml` (flux RSS), `public/llms.txt`
et le bloc « Derniers articles » de `public/index.html`. Une page d'article reçoit aussi un bloc « À lire aussi » dès qu'il
existe un autre article, et un titre de page sans suffixe de marque si le titre complet dépasse 70 caractères. Ne jamais modifier ces
fichiers à la main : ils sont écrasés au build suivant.
