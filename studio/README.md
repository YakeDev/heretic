# Heretic Studio — fondation locale (alpha)

Interface **expérimentale, en français, en lecture seule** pour explorer les informations du moteur Heretic et le matériel de la machine. Le moteur Heretic et ses commandes existantes restent inchangés.

## Périmètre disponible

- Tableau de bord React accessible dans le navigateur en local.
- API FastAPI locale : GET /api/health, GET /api/system, GET /api/project, GET /api/models et GET /api/models/search?q=.
- Vue de la mémoire, du processeur et des GPU NVIDIA détectables par nvidia-smi.
- Métadonnées du paquet Heretic lues depuis pyproject.toml.
- Catalogue local indicatif de modèles Llama, Qwen, Gemma et Mistral.
- Recherche de métadonnées publiques de Hugging Face (connexion internet nécessaire seulement pour la recherche).
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

## Sécurité et architecture

- **Local uniquement** : le serveur est lancé sur 127.0.0.1 ; ne pas utiliser --host 0.0.0.0.
- L'API n'accepte aucune action modifiant ou lançant un modèle ; pas de terminal distant ni d'exécution de commandes arbitraires.
- La seule commande système exécutée par l'API est nvidia-smi avec arguments fixes et délai d'attente.
- Aucune clé Hugging Face n'est demandée, collectée ou sauvegardée.
- La recherche utilise exclusivement https://huggingface.co/api/models avec timeout et limite de résultats ; une entrée ne peut pas choisir une URL distante.
- La recherche renvoie des informations non fiables d'un service tiers : ne pas prendre une fiche pour une preuve de compatibilité ou de sécurité.
- Les licences et accès contrôlés des modèles (dont Meta Llama) doivent être vérifiés sur leurs fiches officielles.
- La configuration originale (config.default.toml) reste inchangée.
- Cette première version **ne prouve pas** que la machine est compatible avec tel ou tel modèle.
- Les tests CUDA, les performances et la compatibilité GPU devront être validés sur une machine réelle.

## Prochain jalon

Un assistant de configuration et un gestionnaire d'expériences **avec confirmation explicite, annulation et journaux** ; ces fonctions ne sont pas présentes dans cette alpha.

Licence : le dépôt parent est sous AGPL-3.0-or-later ; les nouvelles contributions conservent cette licence.
