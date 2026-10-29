# Heretic Studio — principes de conception UX/UI (alpha)

## Objectif

Permettre à un utilisateur de **choisir un modèle, comprendre les ressources nécessaires, télécharger avec consentement et discuter en local**, sans devoir maîtriser l'architecture PyTorch, les dépendances ou les API. Aucune interface ne doit faire croire qu'une optimisation Heretic ou une compatibilité matérielle a été validée si ce n'est pas le cas.

## Architecture de l'information

- **Découvrir** : vue d'ensemble, matériel, modèles.
- **Préparer** : estimation de compatibilité, contrôle des logiciels, téléchargement avec confirmation explicite.
- **Expérimenter** : chat local, futures fonctionnalités.
- Les liens du menu ciblent des sections réelles et le lien actif suit le défilement, y compris dans les sections imbriquées.
- Les trois étapes visibles sur l'accueil indiquent une progression logique sans imposer un assistant bloquant. Le chat est directement accessible aux personnes qui ont déjà un modèle.

## Principes appliqués

| Principe | Application concrète |
| --- | --- |
| Gestalt — proximité et région commune | Regrouper par tâche les contrôles, informations, messages d'erreur et résultats ; cartes au style cohérent. |
| Gestalt — similarité | Mêmes styles pour cartes, labels, contrôles et liens qui jouent le même rôle ; une action principale se distingue des actions secondaires. |
| Gestalt — continuité | Parcours Choisir → Vérifier → Discuter, sans masquer les raccourcis des utilisateurs habitués. |
| Hick-Hyman | Réduire les choix simultanément visibles grâce aux groupes de menu et aux paramètres secondaires repliés. |
| Miller / charge cognitive | Donner une consigne courte et une prochaine action à la fois ; les détails techniques ne doivent pas monopoliser la lecture. |
| Reconnaissance plutôt que rappel | Sélection du modèle conservée durant la session du navigateur ; modèles, états et prochaines actions explicites. |
| Feedback et visibilité de l'état | Backend local connecté/indisponible, chargement du modèle, génération et transfert décrits dans la langue de l'interface. |
| Prévention d'erreur et contrôle | Télécharger uniquement après lecture et acceptation de licence ; compatibilité présentée comme estimation, pas certification. |
| Loi de Fitts | Zones de clic principales d'au moins 44 px de hauteur, états de focus visibles, liens de navigation suffisamment espacés. |
| Divulgation progressive | Détails de performance, tests et réglages avancés du chat repliés par défaut. |

Ces principes sont des *heuristiques de conception*, pas des preuves d'efficacité sans observation d'utilisateurs.

## Système visuel

- **Typographie** : police système sans téléchargement externe, texte principal légèrement plus grand que les labels, contraste renforcé pour les informations de premier niveau. Messages de chat avec hauteur de ligne généreuse.
- **Espacements** : alignement et rythme récurrents (8 / 12 / 16 / 24 / 32 / 48 px), marges internes cohérentes et largeur de lecture limitée.
- **Couleurs** : thème sombre existant conservé ; vert menthe réservé à l'action principale, au focus et à l'état favorable ; ambre pour une attente/limite et rose pour un échec. Les mots accompagnent toujours la couleur.
- **Boutons** : action principale remplie, secondaires bordés ; désactivation seulement lorsqu'une action est réellement impossible.
- **Cartes** : distinction entre métriques matérielles, modèles, contrôles et conversation par leurs régions visuelles.

## Responsive et accessibilité

- Grand écran : barre latérale fixe avec défilement interne si nécessaire, contenu fluide.
- Tablette : navigation horizontale fixe, liens défilables indépendamment et contenu sur une colonne lorsque nécessaire.
- Téléphone : cibles tactiles, menu horizontal défilable, cartes et actions empilées.
- Lien « Passer au contenu principal » au clavier, repères `main` / `nav` / `section`, titres et labels descriptifs, `aria-current` sur l'onglet actif et `aria-live` pour les états.
- Contraste, zoom 200 % et contrôle au clavier restent à **recetter sur navigateurs réels** ; la compilation TypeScript n'atteste pas une conformité WCAG.
- `prefers-reduced-motion` désactive le défilement fluide et les transitions.

## Scénarios de recette manuelle

1. Depuis l'accueil, accéder au chat en un clic, avec ou sans modèle téléchargé.
2. Sélectionner Qwen, actualiser la page : sa sélection est restaurée sans relancer de téléchargement.
3. Parcourir matériel → modèles → compatibilité → logiciels → télécharger → chat : le menu met en évidence la bonne section.
4. Au clavier, utiliser Tab/Entrée et le lien d'évitement ; vérifier que le focus reste toujours visible.
5. Sur une résolution de 375, 768 et 1366 px, vérifier l'absence de chevauchement, de texte tronqué et de navigation inaccessible.
6. Couper le backend : un état de connexion explicite et une action de relance s'affichent, sans succès fictif.
7. Ouvrir le chat : les paramètres avancés et les diagnostics restent facultatifs ; les erreurs et les limites de génération sont lisibles.
8. Tester un modèle avec droits restreints : aucune étape de téléchargement n'est déclenchée avant confirmation de la licence.

## Ce qui n'a pas changé

Les endpoints et contrôles de sécurité côté backend, les modèles existants, l'accès exclusivement local et les exigences d'autorisation du téléchargement. La refonte ne constitue pas un audit ergonomique avec utilisateurs, ni une validation de la qualité factuelle du modèle.
