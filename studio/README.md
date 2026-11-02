# Heretic Studio — fondation locale (alpha)

Interface **expérimentale, en français, en lecture seule** pour explorer les informations du moteur Heretic et le matériel de la machine. Le moteur Heretic et ses commandes existantes restent inchangés.

## Périmètre disponible

- Tableau de bord React accessible dans le navigateur en local.
- API FastAPI locale : GET /api/health, GET /api/system, GET /api/project, GET /api/models et GET /api/models/search?q=.
- Vue de la mémoire, du processeur, de l'espace disque et des GPU NVIDIA détectables par nvidia-smi.
- Métadonnées du paquet Heretic lues depuis pyproject.toml.
- Catalogue local indicatif de modèles Llama, Qwen, Gemma et Mistral.
- Recherche de métadonnées publiques de Hugging Face (connexion internet nécessaire seulement pour la recherche).
- **Estimation indicative des ressources** pour les modèles du catalogue : inférence ou optimisation Heretic, FP16 ou bitsandbytes 4 bits.
- Sélection d'un modèle depuis le catalogue, évaluation locale sans téléchargement ni exécution.
- **Pas de téléchargement des poids, d'exécution, de modification, d'export ni de publication de modèles.** Les commandes futures ne sont pas activées.

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

## Sécurité et architecture

- **Local uniquement** : le serveur est lancé sur 127.0.0.1 ; ne pas utiliser --host 0.0.0.0.
- L'API n'accepte aucune action modifiant ou lançant un modèle ; pas de terminal distant ni d'exécution de commandes arbitraires.
- La seule commande système exécutée par l'API est nvidia-smi avec arguments fixes et délai d'attente.
- Aucune clé Hugging Face n'est demandée, collectée ou sauvegardée.
- La recherche utilise exclusivement https://huggingface.co/api/models avec timeout et limite de résultats ; une entrée ne peut pas choisir une URL distante.
- La recherche renvoie des informations non fiables d'un service tiers : ne pas prendre une fiche pour une preuve de compatibilité ou de sécurité.
- Les licences et accès contrôlés des modèles (dont Meta Llama) doivent être vérifiés sur leurs fiches officielles.
- La configuration originale (config.default.toml) reste inchangée.
- Cette première version **ne prouve pas** que la machine est compatible avec tel ou tel modèle ; l'estimation matérielle est volontairement prudente et non contraignante.
- Les tests CUDA, les performances et la compatibilité GPU devront être validés sur une machine réelle.

## Prochain jalon

Un diagnostic logiciel plus précis (pilotes/CUDA/ROCm/MPS, vérification des architectures), un assistant de configuration et un gestionnaire d'expériences **avec confirmation explicite, annulation et journaux** ; ces fonctions ne sont pas présentes dans cette alpha.

Licence : le dépôt parent est sous AGPL-3.0-or-later ; les nouvelles contributions conservent cette licence.
