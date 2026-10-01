# Guide éditorial d'un article UMPC

Un article ne transcrit pas la vidéo : il en fait un texte à lire, avec plus de précision, les limites de ce qu'on sait
et les sources. Le lecteur arrive souvent depuis une recherche web ou un partage ; il doit comprendre sans avoir vu la
vidéo, mais la vidéo reste le premier élément de la page.

## Matière première du dossier de production

| Fichier | Ce qu'on y prend |
|---|---|
| `Documents/Research.md` | la matière scientifique, **les rubriques « Limites » (elles deviennent les encadrés)**, le niveau d'accès de chaque source (texte intégral, résumé seulement) |
| `Documents/Script_Video.md` | le tableau des affirmations vérifiées : quelle phrase repose sur quelle source, avec la prudence retenue |
| `Documents/Narration.md` | l'ordre et la formulation validés ; ne pas la recopier |
| `Documents/Social_Publishing.md` | titre, chapitres, **sources réellement citées**, crédits d'images déjà rédigés |
| `media/MediaSources.md` | licence, auteur, lien et adaptation de chaque média ; les médias réels y sont distingués des illustrations générées |
| `media/images/`, `Scenes/Scene-N/*_frame.png`, `Montage/*miniature*.png` | images candidates |
| `Montage/*video_finale.mp4` | schémas animés du montage, extractibles avec `video_time` |

Les documents varient d'un épisode à l'autre (les épisodes 1 et 2 n'ont pas le tableau de sources `S1…` de l'épisode 3).
Lire les fichiers entiers plutôt que de se fier au seul rapport de `inspect_production.py`.

## Construire l'article

1. **Un fil conducteur** : la question centrale de la vidéo, posée dans le chapô et reprise dans la conclusion.
2. **Une section par chapitre ou par cas**, dans l'ordre de la vidéo, avec ce schéma : la question, l'organisme ou
   l'objet, le mécanisme expliqué pas à pas, l'encadré « Ce qu'il ne faut pas en conclure », une ou deux figures, le
   bouton vers le chapitre de la vidéo.
3. **Ajouter ce que la vidéo ne peut pas dire** : noms scientifiques (la voix les évite), chiffres précis et leur
   source, contexte. Rester dans ce que les sources établissent : jamais de chiffre, de protocole ou de résultat que le
   dossier ne justifie pas.
4. **Garder les nuances de la vidéo** : « interprétation », « chez la souris », « non établi », « pas un noyau »... Un
   article plus affirmatif que la vidéo est un défaut, pas un gain.
5. Longueur : 5 à 8 minutes de lecture environ pour une vidéo de 4 minutes. La page calcule le temps de lecture.

Français soigné, ton direct et précis, vouvoiement et tutoiement évités (formulations neutres). Guillemets « ». Espaces
insécables (`&nbsp;`) dans les nombres (5&nbsp;000). **Pas de tiret cadratin** (règle des livrables publics du projet).

## Sources : règles

- **Seulement celles qui justifient une information de la vidéo.** Partir des sources de la description YouTube et de
  `Script_Video.md`, jamais d'une liste gonflée. Le build refuse une source jamais citée dans le texte.
- **Publication originale d'abord.** Si un article de presse, une page d'université ou un communiqué traite du même point
  qu'une étude, citer l'étude. Une présentation institutionnelle n'est gardée que si elle apporte une donnée que
  l'étude ne donne pas dans son résumé (exemple de l'article 1 : Berkeley Lab pour « 9,66 mm » et « environ 5 000 fois »),
  et elle est étiquetée comme telle dans `kind`. Écarter une source secondaire qui ne fait que répéter la publication.
- **Métadonnées vérifiées, jamais devinées.** Vérifier titre, revue, année et DOI par une API publique, sans quoi laisser
  « premier auteur et al. » :
  - Europe PMC : `https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:<doi>&format=json&resultType=core`
  - Crossref : `https://api.crossref.org/works/<doi>`
  Ne pas inventer de prénoms ni de co-auteurs. Préférer le lien `https://doi.org/<doi>` à l'URL de l'éditeur.
- **Une affirmation de la vidéo dont la seule source n'est pas dans la description YouTube** (exemple de l'article 1 :
  « certaines bactéries se développent dans les tumeurs », appuyée seulement par une page du NCI) : l'ajouter à la
  bibliographie avec `kind = "Contexte"`, plutôt que de laisser une affirmation sans référence ou de la retirer du texte.
- Partir des sources de la description n'interdit pas d'écarter celles qui ne servent qu'à cadrer la recherche (une page
  d'organisme qui reprend une étude déjà citée). Si le choix est discutable, le signaler à l'utilisateur.
- **Niveau d'accès honnête** : si seul le résumé a été lu (Research.md le précise), le dire dans `method` et ne pas ajouter
  de détail qui exigerait le texte intégral.
- Les sites d'éditeurs répondent souvent 403 aux robots : un lien DOI qui répond 403 n'est pas cassé. Un 404 l'est.

## Images : règles

- **Médias réels d'abord** (micrographies, photos), avec auteur, licence et `credit_url` vers la fiche source. Reprendre
  l'auteur et la licence de `MediaSources.md`, mais pas la formule « À l'écran : ... » : le champ `credit` décrit ce qui a
  été fait **pour le site** (« recadrée », « colorisée »), pas pour le montage vidéo. Une image publiée sans recadrage
  n'est pas « recadrée ».
- **Illustrations et images générées** : `generated = true`, légende qui ne les présente jamais comme une observation.
- **Schémas dérivés d'une publication** (figure retraduite ou redessinée d'après une source libre) : pas de badge
  « Illustration » si le schéma est fidèle à la publication ; `credit` indique la source et la modification
  (« Schéma d'après Volland et al., Science, 2022 · étiquettes traduites ») et `credit_url` pointe vers le fichier source
  libre s'il y en a un. Les scènes générées ou animées par IA gardent `generated = true`.
- **Schémas extraits de la vidéo finale** : pas de `credit_url` ; `credit` = « Schéma de la vidéo, d'après <source> ».
- **Schémas de la vidéo** : extraire avec `video_time` après avoir regardé une planche contact
  (`scripts/contact_sheet.py`) ; éviter les instants à mi-animation, les textes coupés et les images presque vides.
  Un `box` peut recadrer le schéma utile.
- **Image de couverture** : la miniature réellement publiée sur YouTube, pour que la carte, le partage et la vidéo
  concordent. Si plusieurs miniatures existent dans `Montage/`, regarder la miniature affichée par le lecteur de la page
  (ou demander) au lieu de supposer.
- Poids : éviter de choisir des images sources inutilement énormes ; le générateur redimensionne, mais les fichiers de
  plus de 10 Mo ralentissent le build.

## Relecture éditoriale avant de rendre la main

Le build et l'aperçu (étape 6 du `SKILL.md`) contrôlent la forme ; ceci contrôle le fond.

1. Relire le texte contre `Research.md` : chaque encadré « Ce qu'il ne faut pas en conclure » correspond à une limite
   réelle ; aucune affirmation ne dépasse la vidéo.
2. Dire à l'utilisateur ce qui reste à confirmer : date de mise en ligne, sources lues en résumé, choix des sources
   écartées ou ajoutées, image de couverture.

## Pièges rencontrés avec le premier article

- La date de mise en ligne de la vidéo n'est dans aucun fichier : la demander, sinon la signaler comme supposée.
- L'inventaire peut être maigre (formats différents) : relire les documents, ne pas conclure qu'il n'y a pas de source.
- Les images extraites de la vidéo sont souvent à mi-animation : toujours passer par une planche contact.
- La miniature « recommandée » de `Social_Publishing.md` n'est pas forcément celle qui a été publiée (épisode 3 : la
  recommandée était « Une seule cellule ? », la publiée « Une boussole ? »). L'inventaire compare la miniature YouTube
  aux fichiers de `Montage/` et désigne la bonne.
- Les prénoms et listes de co-auteurs qu'on « croit connaître » sont une source d'erreurs : vérifier ou s'abstenir.
