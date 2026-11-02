# Heretic Studio — application locale (alpha)

Interface **expérimentale, en français, locale, avec diagnostics, téléchargement facultatif et premier chat IA local** pour explorer les informations du moteur Heretic et le matériel de la machine. Le moteur Heretic et ses commandes existantes restent inchangés.

Pour la conception visuelle, les principes d'ergonomie cognitive et les scénarios de recette, voir [Principes UX/UI](UX_UI_GUIDELINES.md).

## Périmètre disponible

- Tableau de bord React accessible dans le navigateur en local.
- Barre latérale fixe à l'écran sur ordinateur pendant le défilement de la page ; si les liens dépassent la hauteur disponible, défilement interne du menu. Sous 951 px, barre de navigation horizontale non fixe avec défilement latéral des liens, afin de préserver la place sur petit écran.
- API FastAPI locale : GET /api/health, GET /api/system, GET /api/project, GET /api/models et GET /api/models/search?q= ; endpoints de téléchargement opt-in (voir ci-dessous).
- Vue de la mémoire, du processeur, de l'espace disque et des GPU NVIDIA détectables par nvidia-smi.
- Métadonnées du paquet Heretic lues depuis pyproject.toml.
- Catalogue local indicatif de modèles Llama, Qwen, Gemma et Mistral.
- Recherche de métadonnées publiques de Hugging Face (connexion internet nécessaire seulement pour la recherche).
- **Estimation indicative des ressources** pour les modèles du catalogue : inférence ou optimisation Heretic, FP16 ou bitsandbytes 4 bits.
- Sélection d'un modèle depuis le catalogue, évaluation locale sans téléchargement ni exécution.
- Diagnostic logiciel déclenché explicitement : versions Python/PyTorch/Transformers/Accelerate/PEFT/bitsandbytes/Hugging Face Hub/Optuna, pilotes NVIDIA accessibles et sondage local PyTorch CUDA/Apple MPS.
- Téléchargement local **seulement après une vérification des métadonnées, de l'espace disque et une confirmation de licence** ; annulation disponible.
- Chat IA local facultatif : chargement d'un snapshot téléchargé dans un processus enfant isolé, réponses courtes, arrêt manuel et libération des ressources.
- **Aucune optimisation Heretic, modification, export ni publication de modèle n'est activée.** L'inférence ne modifie pas les poids.

## Lancer le backend (terminal 1)

Depuis la racine du dépôt (Python 3.10+) :

~~~sh
cd studio/backend
python -m venv .venv
# Linux/macOS : source .venv/bin/activate
# Windows PowerShell : .venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8765
~~~

## Lancer le frontend (terminal 2)

Node.js >= 20.19 requis pour Vite 7.

~~~sh
cd studio/frontend
npm install
npm run dev
~~~

Puis ouvrir http://127.0.0.1:5173.

## Vérifications backend

~~~sh
cd studio/backend
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
~~~

Vérifier le frontend avec `npm run build`. Le workflow `Heretic Studio checks` automatise ces deux suites de vérifications.

## Estimation matérielle

Dans l'interface, sélectionner **Évaluer mon matériel** sous un modèle, choisir l'usage (inférence ou optimisation Heretic), la précision, puis cliquer **Analyser les ressources**.

Endpoint local : `GET /api/hardware/estimate?model_id=meta-llama/Llama-3.2-3B-Instruct&mode=inference&precision=fp16`

Le moteur produit des **ordres de grandeur** (en Gio, base 1024³) à partir du nombre approximatif de paramètres affiché dans notre catalogue :
- poids FP16 : environ **2 octets / paramètre** ; bitsandbytes 4 bits : **0,5 octet / paramètre**, avant surcoûts réels ;
- inférence FP16 : environ `1,3 × poids + 2 Gio` de VRAM ; inférence 4 bits : `1,5 × poids + 3 Gio` ;
- optimisation FP16 : environ `2 × poids + 6 Gio` ; optimisation 4 bits : `2,5 × poids + 6 Gio` ;
- RAM indicative : `max(8 Gio, 1,3 × poids + 4 Gio)` ;
- stockage indicatif : `1,5 × poids + 3 Gio`.

Ces **heuristiques ne sont pas des seuils réels d'Heretic** : la mémoire nécessaire dépend également de l'architecture, de la longueur de séquence, des activations, des paramètres ARA/LoRA, de la configuration PEFT, de la quantification et du logiciel. Elles servent uniquement à repérer des contraintes évidentes, pas à valider un appareil.

### Comment lire le résultat ?

| Statut | Signification |
| --- | --- |
| Ressources potentiellement suffisantes | Le meilleur GPU NVIDIA détecté semble avoir assez de VRAM libre selon notre estimation, et le disque ne présente pas de manque identifié. **La compatibilité n'est pas confirmée.** |
| Ressources probablement insuffisantes | Manque évident de VRAM NVIDIA détectée ou de disque disponible par rapport à notre budget indicatif. Une autre configuration peut fonctionner. |
| Diagnostic indéterminé | Pas de GPU NVIDIA détecté ou manque d'informations (AMD, CPU, Apple Silicon, autres accélérateurs). **Ce n'est pas un verdict d'incompatibilité.** |

- **Plusieurs GPU :** on utilise le GPU individuel avec le plus de mémoire libre et **jamais la somme** de la VRAM des cartes, car le parallélisme n'est pas garanti.
- **CPU, AMD et Apple Silicon :** fonctionnement non évalué par notre sonde NVIDIA ; la présence ou absence de GPU n'est pas une preuve de prise en charge.
- **Disque :** l'espace libre est calculé sur le disque contenant le projet, pas nécessairement sur le chemin final de téléchargement.
- **RAM :** la mémoire disponible est un instantané ; des applications parallèles peuvent la faire varier.
- **Compatibilité réelle :** non testée (pilotes, CUDA/ROCm/MPS, bitsandbytes, PyTorch, architecture, licence). Les modèles ne sont pas lancés.
- **Modèles non répertoriés :** réponse HTTP 404 au lieu d'inventer une estimation de paramètres.

## Diagnostic logiciel (étape suivante)

Depuis l'interface de Heretic Studio, cliquer **Vérifier mon environnement**.
Cette action appelle `GET /api/hardware/software` et ne requiert aucun modèle.

Le diagnostic :

- lit les versions des distributions Python **sans importer leurs modules** (via `importlib.metadata`) ;
- examine les informations de pilote NVIDIA si `nvidia-smi` est disponible ; une sonde manquante **ne prouve pas l'absence de GPU** ;
- exécute uniquement une **sonde PyTorch codée en dur**, via `python -I -c` dans un **processus enfant isolé**, avec délai maximum de 15 secondes ;
- vérifie si PyTorch déclare CUDA ou Apple MPS disponibles et relève les versions CUDA/ROCm de son build ;
- n'importe aucun code distant, ne télécharge pas de poids, n'installe rien, ne modifie pas la configuration de l'ordinateur.

### Interprétation

- `torch_not_installed` : PyTorch absent **du Python exécutant le backend Studio**. Il peut être présent dans un autre environnement.
- `checked` : la sonde Python a pu lire les informations de PyTorch ; cela ne prouve pas qu'Heretic peut charger le modèle choisi.
- `probe_failed` / `timeout` : diagnostic non concluant, aucune déduction de compatibilité.
- `not_detected` pour le pilote NVIDIA : absence de résultat de la commande, pas preuve d'incompatibilité AMD/Apple.
- Versions de bibliothèques installées : **ne démontrent ni cohérence entre versions, ni disponibilité du backend 4 bits.**

L'application affiche toujours `compatibility: not_verified`. Le diagnostic concerne **l'environnement du backend Studio**, et non automatiquement le Python d'une autre installation de Heretic. L'exécution réelle, la compatibilité d'architecture des modèles et l'acceptation des licences sont hors périmètre.

### Vérifications automatisées

Tests : `python -m unittest discover -s studio/backend/tests -v`, et compilation React `cd studio/frontend && npm run build`. Les tests utilisent des mocks pour ne pas lancer réellement PyTorch ou `nvidia-smi`.

## Téléchargement facultatif des modèles (alpha)

Cette étape permet de préparer et télécharger des fichiers de modèles, **mais pas encore de discuter avec eux**. L'inférence et la comparaison seront développées séparément.

1. Dans le catalogue, sélectionner un modèle répertorié.
2. Dans la section « Télécharger les fichiers du modèle », cliquer « Vérifier les fichiers et le stockage ».
3. Examiner **la taille réelle indiquée par les métadonnées Hugging Face**, l'espace disponible, la révision épinglée et la fiche de licence.
4. Accepter les conditions **uniquement si l'on possède les droits nécessaires**, puis confirmer le téléchargement.
5. Consulter la progression par fichiers entièrement reçus ; l'annulation arrête le processus enfant. Les téléchargements partiels peuvent être conservés et repris par le client Hugging Face.

L'application ne télécharge pas automatiquement. Elle ne demande jamais de token. Les modèles à accès contrôlé (Meta Llama notamment) requièrent l'accord du détenteur des droits et, si nécessaire, une authentification préalable avec la CLI officielle Hugging Face dans le système local.

### API locale

- `GET /api/downloads/session` — initie une session avec protection anti-CSRF, réservée à l'origine du frontend.
- `POST /api/downloads/preview` — récupère les métadonnées du modèle **du catalogue uniquement**, sans poids, et valide les ressources.
- `POST /api/downloads/start` — démarre un processus de téléchargement sur confirmation explicite.
- `GET /api/downloads/{job_id}` — état et progression par fichiers terminés.
- `POST /api/downloads/{job_id}/cancel` — arrêt du processus de téléchargement.

Les requêtes sur ces endpoints requièrent une origine locale autorisée et l'en-tête `X-Heretic-Token`. Le serveur est destiné à `127.0.0.1:8765`, et non à un hébergement Internet.

### Garanties et limites

- **Autorisation préalable :** seuls les modèles prédéfinis dans `studio/backend/catalog.py` sont téléchargeables dans cette version.
- **Révision immuable :** la liste de fichiers est obtenue depuis Hugging Face puis épinglée au SHA de commit renvoyé.
- **Formats :** seuls les fichiers statiques, tokenizers et `.safetensors` sont admis. Les exécutables Python et poids pickle/`.bin` sont rejetés.
- **Budget de téléchargement :** 35 Gio maximum par modèle et 350 fichiers, avec contrôle d'espace disque et marge de sécurité.
- **Dossier :** `~/.cache/heretic-studio/models/<organisation--modele>/<revision>` ; les fichiers de progression restent dans `~/.cache/heretic-studio/jobs`.
- **Processus indépendant :** le téléchargement fonctionne sans exécuter du code de modèle ; l'annulation termine le processus enfant.
- **Un seul transfert actif à la fois** afin de limiter la consommation de ressources.
- **Progression :** les octets d'un fichier ne sont comptés qu'après le téléchargement complet de ce fichier, donc la barre peut rester immobile pendant un gros fichier.
- **Environnement :** le client Hugging Face lit l'authentification locale éventuelle configurée par son outil officiel. Il n'existe pas encore d'interface de login dans Studio.
- **Limites :** l'examen des tailles et la marge libre ne garantissent ni la capacité réelle du cache, ni les performances, ni la compatibilité du modèle sur l'ordinateur.

Pour le **premier test de conversation réel**, il faudra encore implémenter le chargement du modèle (inférence), contrôler l'architecture et utiliser une machine suffisamment dotée.

## Premier test réel d'un modèle en chat local (alpha)

**Cette fonctionnalité nécessite une machine compatible :** la réussite des tests GitHub ne prouve pas que ton GPU, tes pilotes ou ta RAM permettent de charger Llama ou Qwen.

### Installation facultative des dépendances d'inférence

Le backend de diagnostic reste léger : ni PyTorch ni Transformers ne sont requis pour simplement consulter les modèles. Pour **activer le chat**, installer séparément, **dans le même environnement Python que le backend Studio**, la pile d'inférence :

~~~sh
cd studio/backend
python -m pip install -r requirements-inference.txt
~~~

Pour un GPU NVIDIA, choisir au préalable **la version de PyTorch adaptée au pilote et à CUDA**, en suivant les instructions officielles de PyTorch. Le `pip install` générique peut installer une version CPU seulement ou une variante CUDA inadaptée. Les modes GPU AMD/ROCm et Apple MPS ne sont **pas encore intégrés au module de chat** : ils nécessitent des essais dédiés.

### Parcours d'essai

1. Ouvrir Heretic Studio sur `http://127.0.0.1:5173` avec le backend local démarré sur `127.0.0.1:8765`.
2. Sélectionner un modèle du catalogue, puis effectuer le **téléchargement explicitement confirmé**. Le téléchargement doit être **complet** pour créer une attestation locale de snapshot.
3. Pour un premier essai sur un ordinateur sans GPU puissant, privilégier **Qwen2.5-0.5B-Instruct**, plus léger que Llama 3B ou 8B. Dans la section **Premier chat local**, cliquer « Actualiser les modèles téléchargés ».
4. Choisir le modèle et son matériel (**GPU NVIDIA CUDA**, ou **CPU expérimental et potentiellement très lent**). Les ressources sont comparées à un budget approximatif avant le démarrage.
5. Cliquer « Charger le modèle ». Le processus isolé charge les poids `.safetensors`, sans connexion réseau, sans exécution de code distant et sans faire d'optimisation Heretic.
6. Lorsque l'état indique **ready**, envoyer une question de test, par exemple « Explique-moi TCP et UDP ».
7. Cliquer **Arrêter le modèle** pour terminer le processus enfant et libérer la mémoire.

### API locale

Les routes ci-dessous utilisent les mêmes contrôles **Host local + Origin autorisée + jeton X-Heretic-Token** que le gestionnaire de téléchargement :

- `GET /api/chat/models` : snapshots locaux vérifiés avec reçu de téléchargement complet.
- `GET /api/chat/current` : retrouver la session de chargement déjà active après un rechargement de la page.
- `POST /api/chat/start` : demande explicite de chargement (`model_id`, `revision`, `device` = `cuda` ou `cpu`).
- `GET /api/chat/{session_id}` : état `loading`, `ready`, `failed`, `generating`, `stopped`.
- `POST /api/chat/{session_id}/generate` : envoi d'une conversation bornée.
- `GET /api/chat/{session_id}/responses/{request_id}` : consultation de la réponse générée.
- `POST /api/chat/{session_id}/stop` : terminaison du processus d'inférence.

### Limitations et protections

- **Modèles :** premier chat limité à quelques architectures textuelles du catalogue (Llama, Qwen3, Mistral). La présence dans le catalogue ne prouve pas la compatibilité. Gemma 3 n'est pas encore activé dans le chat car son chemin multimodal doit être vérifié séparément.
- **Poids :** chargement uniquement depuis un dossier créé par le téléchargement du gestionnaire Studio, doté d'un reçu valide et de fichiers réguliers, sans liens symboliques. `config.json` doit annoncer le type d'architecture attendu, sans `auto_map` distant.
- **Sécurité :** `trust_remote_code=False`, `local_files_only=True`, `use_safetensors=True`, `HF_HUB_OFFLINE=1`. Les fichiers de modèles restent des contenus externes ; ces précautions ne constituent pas une sandbox de sécurité absolue.
- **Capacité :** une seule session chargée et une seule génération en cours ; mémoire RAM/VRAM vérifiée selon des heuristiques prudentes. La vérification ne remplace pas un vrai essai.
- **Messages :** maximum 12 messages, 2 000 caractères par message, 6 000 caractères de contexte texte, 192 nouveaux tokens. Ils ne sont pas envoyés vers un serveur externe par ce module. Les réponses passent temporairement par des fichiers locaux de progression, effacés normalement après lecture ou à l'arrêt ; une panne peut laisser des résidus à supprimer dans `~/.cache/heretic-studio/jobs`.
- **Annulation :** l'arrêt termine le processus enfant ; en cas de mémoire insuffisante, le chargement peut échouer. Une génération lente peut être interrompue en arrêtant la session.
- **Responsabilité :** réponses expérimentales, potentiellement erronées. Ce chat ne supprime pas automatiquement les mécanismes de refus et ne modifie aucun modèle.
- **Cloud :** cette API est destinée exclusivement à l'ordinateur local ; **ne jamais exposer le port 8765 sur Internet**. Une version serveur nécessitera une autre conception (authentification, isolation multiutilisateur, quotas, contrôle d'accès et protection de l'infrastructure).

### Compatibilité Transformers 5 — génération de chat

À partir des versions récentes de Transformers, `apply_chat_template(..., return_tensors="pt")`
peut renvoyer un objet `BatchEncoding` contenant les entrées nommées
`input_ids` et `attention_mask`, et non un tenseur unique.
Le chat prépare désormais explicitement `return_dict=True` et passe les
entrées à `model.generate(**inputs)`, au lieu de les envoyer en argument
positionnel. Cette correction ne nécessite **aucun nouveau téléchargement du
modèle ni réinstallation de PyTorch**.

Si le modèle affiche `ready` mais que la réponse échoue, la zone rouge
indique maintenant **l'étape et la classe d'erreur** sans afficher les
exceptions brutes ni le contenu de la conversation. Le texte de la question
reste dans le champ de saisie pour un nouvel essai. Les tests automatisés
simulent la génération et ne remplacent pas un essai réel sur la carte graphique.

#
## Tester systématiquement la qualité de Qwen (sans téléchargement)

La réussite technique (chargement, réponse et métriques) ne signifie **pas** que
les réponses sont correctes. Nous avons ajouté un mini-benchmark **local et
reproductible**, composé de **16 scénarios / 21 questions** en français :
TCP/UDP, correction d'une erreur, reformulation, contexte, logique, traduction,
JSON, grammaire, code, calculs et reconnaissance de l'incertitude.

Ce sont des **données de test rédigées pour le projet** dans
`studio/backend/benchmarks/french_quality_v2.json` (par défaut).
L'ancienne suite `french_quality_v1.json` est conservée pour reproduire
les premiers résultats (avec son scénario de correction imparfait).
La commande `--suite v1` permet de la rejouer. Elles ne sont ni un
corpus d'entraînement de Qwen, ni une étude représentative de sa fiabilité.
Le script ne fait **aucune requête Internet, aucune installation et aucun
téléchargement de modèle**. Il réutilise seulement le modèle **déjà chargé**
dans Heretic Studio.

1. Lancer le backend et le frontend, ouvrir **Chat local** et **Charger le
   modèle** Qwen ; attendre « Modèle prêt à répondre ».
2. Dans un **troisième terminal**, depuis `studio/backend`, exécuter :

~~~powershell
.\.venv\Scripts\python.exe benchmark_chat.py --limit 3 --mode stable
~~~

3. Pour toute la batterie en mode déterministe (plus long) :

~~~powershell
.\.venv\Scripts\python.exe benchmark_chat.py --all --mode stable
~~~

4. Pour comparer les formulations avec échantillonnage contrôlé :

~~~powershell
.\.venv\Scripts\python.exe benchmark_chat.py --all --mode varied
~~~

Sous Linux/macOS, remplacer `.\.venv\Scripts\python.exe` par
`./.venv/bin/python`. On peut aussi préciser `--max-tokens 64` ou
`--limit 5` pour réduire le temps de calcul. **N'envoyer aucune autre
question dans le chat pendant l'exécution du script**, car le backend ne
permet qu'une génération à la fois.

Dans la v2, le deuxième tour TCP/UDP ne prête plus au modèle une
affirmation qu'il n'a pas forcément faite, et le premier tour n'est plus
automatiquement « réussi » parce que le texte contient le mot TCP.
Ne pas comparer directement les scores formels de v1 et de v2.

Chaque exécution enregistre son rapport **sur l'ordinateur uniquement** sous
`~/.cache/heretic-studio/benchmarks/`, avec les questions, réponses, temps,
tokens, évaluations de forme et **critères de correction humaine**. Le rapport
peut contenir les réponses du modèle : ne pas y ajouter des données privées.
Les contrôles automatiques vérifient uniquement certains formats simples
(nombre exact, JSON, présence d'un mot, nombre approximatif de phrases ou
réponse non identique) ; **ils ne constituent pas un score d'exactitude
factuelle**. Lire les réponses avec leurs références manuelles avant de
conclure qu'un modèle est bon ou mauvais.

### Chat : nouvelle conversation et modes de génération

- **Nouvelle conversation** : efface l'historique affiché et envoyé au
  modèle, sans décharger les poids ni relancer PyTorch. Accessible lorsque
  le modèle est prêt et qu'aucune réponse n'est en cours.
- **Stable** : génération déterministe, adaptée à la reproductibilité.
- **Varié** : température `0.7`, `top_p=0.9`, pénalité de répétition `1.08`.
  Il peut varier les formulations, **sans corriger à lui seul les faits**.
- Une comparaison prudente des dernières réponses affiche un avertissement
  si un texte se répète presque à l'identique. Cet avertissement ne dit
  pas si la réponse est vraie.

## Améliorations du chat local : longueur, Markdown et métriques

- Trois styles de consigne **fixes et locaux** : concis, standard, pédagogique.
  Ils guident le modèle mais **n'assurent pas** qu'il respectera le nombre de
  phrases demandé, ni que ses réponses seront exactes (notamment Qwen 0,5B).
- Longueur réglable dans l'interface : **128, 256, 384 ou 512** nouveaux tokens,
  au lieu d'un plafond systématique de 128 dans l'UI. Une réponse interrompue
  par la limite affiche une alerte explicite.
- Rendu local sécurisé d'un **sous-ensemble de Markdown** : paragraphes, titres,
  gras, italique, listes et blocs de code ; contenu interprété comme du texte
  React, **sans HTML brut, liens exécutables ou bibliothèque supplémentaire**.
- Affichage, par réponse, des tokens générés, de la durée de génération et de
  la vitesse (tokens/s). Sur CUDA, synchronisation avant et après la génération
  pour améliorer l'exactitude. RAM du **processus d'inférence**, VRAM **allouée
  par PyTorch** et pic alloué depuis le chargement sont relevés après réponse.
  Ces valeurs n'incluent pas toutes les allocations des pilotes ou des autres
  applications. Les instantanés de RAM et VRAM libres sur la machine sont
  indiqués séparément : ce ne sont pas des mesures propres au seul modèle.
- Deux questions de test préremplies facilitent la comparaison manuelle, sans
  inventer de score automatique d'exactitude.
- Limites conservées : une session et une génération à la fois, 12 messages
  maximum et 6 000 caractères au total, aucune optimisation Heretic activée.

Pour obtenir ces améliorations : `git pull --ff-only origin feature/heretic-studio-local-chat`,
redémarrer Uvicorn, puis rafraîchir Chrome. Aucun nouvel achat de données :
**pas de dépendance npm ajoutée, pas de nouveau modèle et pas de réinstallation
de PyTorch**.

### Tests

Les tests automatisés vérifient les conditions de sécurité et simulent le processus enfant ; **ils ne chargent pas de vrai modèle**. La dernière étape de recette est un essai manuel de téléchargement + démarrage + conversation + arrêt sur un GPU compatible.

## Récupérer le téléchargement interrompu de Qwen2.5-0.5B sans Internet

Sur certaines sessions Windows, le processus de téléchargement a pu s'arrêter **après** avoir transféré les fichiers, mais **avant** d'écrire `heretic-studio-snapshot.json`. Le dossier contient alors huit fichiers, alors que le journal reste à 7/8. **Ne recommence pas un téléchargement de 1 Go avant de vérifier les fichiers existants.**

Dans PowerShell, après avoir récupéré la dernière version de la branche, ouvrir `studio/backend` et exécuter :

~~~powershell
.\\.venv\\Scripts\\python.exe recover_snapshot.py
~~~

La vérification est **entièrement hors ligne et non destructive**. Pour cette première récupération, elle est délibérément limitée à **Qwen/Qwen2.5-0.5B-Instruct**, avec les huit fichiers attendus, le total connu de **999 591 264 octets**, une révision Git Hugging Face cohérente et une trace locale du téléchargement dans `~/.cache/heretic-studio/jobs`. Elle recalcule une empreinte cryptographique de chaque fichier et la compare aux métadonnées Hugging Face locales (SHA-256 pour les poids LFS, SHA-1 avec préfixe Git blob pour les fichiers Git). L'égalité des tailles seules n'est **pas** une preuve d'intégrité.

Si et seulement si le résultat affiche **VÉRIFICATION RÉUSSIE**, enregistrer le reçu :

~~~powershell
.\\.venv\\Scripts\\python.exe recover_snapshot.py --repair
~~~

Le mode `--repair` n'utilise pas le réseau, **ne télécharge aucun modèle**, et n'écrit que le fichier de validation final, après tous les contrôles. S'il manque un fichier, une métadonnée ou si une empreinte ne correspond pas, il **refuse l'opération sans créer de reçu**. Ensuite, dans l'interface **Chat local**, cliquer « Actualiser les modèles téléchargés » ; Qwen devrait apparaître.

Cette récupération ciblée des fichiers déjà présents n'est **pas** un système général de reprise des téléchargements. Le rétablissement de la progression après fermeture du navigateur et la gestion des autres modèles seront traités séparément.

## Sécurité et architecture

- **Local uniquement** : le serveur est lancé sur 127.0.0.1 ; ne pas utiliser --host 0.0.0.0.
- L'API n'accepte aucune action modifiant ou exécutant un modèle ; seuls les téléchargements explicitement confirmés sont autorisés, sans terminal distant ni commande arbitraire.
- Les diagnostics utilisent nvidia-smi et une sonde PyTorch encadrée ; le téléchargement lance uniquement un worker Python interne avec arguments fixes.
- Aucune clé Hugging Face n'est demandée, collectée ou sauvegardée.
- La recherche utilise exclusivement https://huggingface.co/api/models avec timeout et limite de résultats ; une entrée ne peut pas choisir une URL distante.
- La recherche renvoie des informations non fiables d'un service tiers : ne pas prendre une fiche pour une preuve de compatibilité ou de sécurité.
- Les licences et accès contrôlés des modèles (dont Meta Llama) doivent être vérifiés sur leurs fiches officielles.
- La configuration originale (config.default.toml) reste inchangée.
- Cette première version **ne prouve pas** que la machine est compatible avec tel ou tel modèle ; l'estimation matérielle est volontairement prudente et non contraignante.
- Les tests CUDA, les performances et la compatibilité GPU devront être validés sur une machine réelle.

## Prochain jalon

La validation réelle des versions, des pilotes, des architectures et du mode bitsandbytes sur une machine de test, un assistant de configuration et un gestionnaire d'expériences **avec confirmation explicite, annulation et journaux** ; ces fonctions ne sont pas présentes dans cette alpha.

Licence : le dépôt parent est sous AGPL-3.0-or-later ; les nouvelles contributions conservent cette licence.
