# Heretic Studio — application locale (alpha)

Interface **expérimentale, en français, locale, avec diagnostic en lecture seule et téléchargement facultatif** pour explorer les informations du moteur Heretic et le matériel de la machine. Le moteur Heretic et ses commandes existantes restent inchangés.

## Périmètre disponible

- Tableau de bord React accessible dans le navigateur en local.
- API FastAPI locale : GET /api/health, GET /api/system, GET /api/project, GET /api/models et GET /api/models/search?q= ; endpoints de téléchargement opt-in (voir ci-dessous).
- Vue de la mémoire, du processeur, de l'espace disque et des GPU NVIDIA détectables par nvidia-smi.
- Métadonnées du paquet Heretic lues depuis pyproject.toml.
- Catalogue local indicatif de modèles Llama, Qwen, Gemma et Mistral.
- Recherche de métadonnées publiques de Hugging Face (connexion internet nécessaire seulement pour la recherche).
- **Estimation indicative des ressources** pour les modèles du catalogue : inférence ou optimisation Heretic, FP16 ou bitsandbytes 4 bits.
- Sélection d'un modèle depuis le catalogue, évaluation locale sans téléchargement ni exécution.
- Diagnostic logiciel déclenché explicitement : versions Python/PyTorch/Transformers/Accelerate/PEFT/bitsandbytes/Hugging Face Hub/Optuna, pilotes NVIDIA accessibles et sondage local PyTorch CUDA/Apple MPS.
- Téléchargement local **seulement après une vérification des métadonnées, de l'espace disque et une confirmation de licence** ; annulation disponible.
- **Pas d'exécution, de modification, d'export ni de publication de modèles.** Ces commandes ne sont pas activées.

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
