<img width="128" align="right" alt="Logo" src="https://github.com/user-attachments/assets/df5f2840-2f92-4991-aa57-252747d7182e" />

# Heretic: Fully automatic censorship removal for language models<br><br>[![Discord](https://img.shields.io/discord/1447831134212984903?color=5865F2&label=discord&labelColor=black&logo=discord&logoColor=white&style=for-the-badge)](https://discord.gg/gdXc48gSyT) [![Matrix](https://img.shields.io/badge/Matrix-black?logo=matrix&style=for-the-badge)](https://matrix.to/#/#heretic:matrix.org) [![Follow us on Hugging Face](https://huggingface.co/datasets/huggingface/badges/resolve/main/follow-us-on-hf-md-dark.svg)](https://huggingface.co/heretic-org) [![Codeberg mirror](https://img.shields.io/badge/Codeberg%20mirror-black?logo=codeberg&style=for-the-badge)](https://codeberg.org/p-e-w/heretic)

[![#1 Repository of the Day](https://trendshift.io/api/badge/repositories/20538)](https://trendshift.io/repositories/20538)

> **Ce fork inclut [Heretic Studio](#heretic-studio--notre-interface-locale-fork-expérimental) : une interface française pour découvrir, télécharger et tester des modèles IA en local.** [Installation](#installation-rapide--windows-powershell--vs-code) · [Utilisation](#premiers-pas-dans-linterface) · [Limites](#sécurité-confidentialité-et-limites). Le projet Heretic original est décrit ci-dessous.

Heretic is a tool that removes censorship (aka "safety alignment") from
transformer-based language models without expensive post-training.
It combines an advanced implementation of directional ablation, also known
as "abliteration" ([Arditi et al. 2024](https://arxiv.org/abs/2406.11717),
Lai 2025 ([1](https://huggingface.co/blog/grimjim/projected-abliteration),
[2](https://huggingface.co/blog/grimjim/norm-preserving-biprojected-abliteration))),
with a TPE-based parameter optimizer powered by [Optuna](https://optuna.org/).

This approach enables Heretic to work **completely automatically.** Heretic
finds high-quality abliteration parameters by co-minimizing the number of
refusals and the KL divergence from the original model. This results in a
decensored model that retains as much of the original model's intelligence
as possible. Using Heretic does not require an understanding of transformer
internals. In fact, anyone who knows how to run a command-line program
can use Heretic to decensor language models.

Heretic supports most dense models, including many multimodal models,
several different MoE architectures, and even some hybrid models like Qwen3.5.
Pure state-space models and certain other research architectures are not yet
supported out of the box.

<img width="650" height="715" alt="Screenshot" src="https://github.com/user-attachments/assets/d71a5efa-d6be-4705-a817-63332afb2d15" />

&nbsp;

Running unsupervised with the default configuration, Heretic can produce
decensored models that rival the quality of abliterations created manually
by human experts:

| Model | Refusals for "harmful" prompts | KL divergence from original model for "harmless" prompts |
| :--- | ---: | ---: |
| [google/gemma-3-12b-it](https://huggingface.co/google/gemma-3-12b-it) (original) | 97/100 | 0 *(by definition)* |
| [mlabonne/gemma-3-12b-it-abliterated-v2](https://huggingface.co/mlabonne/gemma-3-12b-it-abliterated-v2) | 3/100 | 1.04 |
| [huihui-ai/gemma-3-12b-it-abliterated](https://huggingface.co/huihui-ai/gemma-3-12b-it-abliterated) | 3/100 | 0.45 |
| **[p-e-w/gemma-3-12b-it-heretic](https://huggingface.co/p-e-w/gemma-3-12b-it-heretic) (ours)** | **3/100** | **0.16** |

The Heretic version, generated without any human effort, achieves the same
level of refusal suppression as other abliterations, but at a much lower
KL divergence, indicating less damage to the original model's capabilities.
*(You can reproduce those numbers using Heretic's built-in evaluation functionality,
e.g. `heretic --model google/gemma-3-12b-it --evaluate-model p-e-w/gemma-3-12b-it-heretic`.
Note that the exact values might be platform- and hardware-dependent.
The table above was compiled using PyTorch 2.8 on an RTX 5090.)*

Of course, mathematical metrics and automated benchmarks never tell the whole
story, and are no substitute for human evaluation. Models generated with
Heretic have been well-received by users (links and emphasis added):

> "I was skeptical before, but I just downloaded
> [**GPT-OSS 20B Heretic**](https://huggingface.co/p-e-w/gpt-oss-20b-heretic)
> model and holy shit. It gives properly formatted long responses to sensitive topics,
> using the exact uncensored words that you would expect from an uncensored model,
> produces markdown format tables with details and whatnot. Looks like this is
> the best abliterated version of this model so far..."
> [*(Link to comment)*](https://old.reddit.com/r/LocalLLaMA/comments/1oymku1/heretic_fully_automatic_censorship_removal_for/np6tba6/)

> "[**Heretic GPT 20b**](https://huggingface.co/p-e-w/gpt-oss-20b-heretic)
> seems to be the best uncensored model I have tried yet. It doesn't destroy a
> the model's intelligence and it is answering prompts normally would be
> rejected by the base model."
> [*(Link to comment)*](https://old.reddit.com/r/LocalLLaMA/comments/1oymku1/heretic_fully_automatic_censorship_removal_for/npe9jng/)

> "[[**Qwen3-4B-Instruct-2507-heretic**](https://huggingface.co/p-e-w/Qwen3-4B-Instruct-2507-heretic)]
> Has been the best unquantized abliterated model that I have been able to run on 16gb vram."
> [*(Link to comment)*](https://old.reddit.com/r/LocalLLaMA/comments/1phjxca/im_calling_these_people_out_right_now/nt06tji/)

Heretic models have also been independently benchmarked using standard metrics
like MMLU and GSM8K, and have been found to compare favorably with models
produced by competing abliteration tools:
[1](https://old.reddit.com/r/LocalLLaMA/comments/1sojjoc/abliterlitics_benchmark_and_tensor_analysis/),
[2](https://old.reddit.com/r/LocalLLaMA/comments/1sy18lx/abliterlitics_benchmarks_and_tensor_comparison/).

The community has created and published
[well over 5000](https://huggingface.co/models?other=heretic)
models with Heretic.


## Heretic Studio — notre interface locale (fork expérimental)

> [!NOTE]
> **Deux projets coexistent dans ce dépôt.**
> - **Heretic original** : moteur Python en ligne de commande pour l'abliteration et l'optimisation de modèles. La documentation d'origine est conservée dans la section [Usage](#usage) ci-dessous.
> - **Heretic Studio** : interface **React + FastAPI**, ajoutée dans ce fork pour découvrir les modèles, examiner son matériel, télécharger certains poids après confirmation et **discuter avec un modèle exécuté localement**. Le chat Studio **n'effectue aucune abliteration** et ne modifie pas les poids des modèles.
>
> Studio est une **alpha expérimentale, non officielle et non fusionnée dans le projet amont**. Pour le moment, elle est développée sur la branche **`feature/heretic-studio-local-chat`**. Cloner seulement la branche `master` du fork ne suffit pas à obtenir cette version.

### Pourquoi cette évolution ?

Le moteur Heretic d'origine suppose une certaine aisance avec Python, les terminaux et les modèles de langage. Notre objectif est de proposer une entrée plus accessible, guidée et transparente : **comprendre sa machine → choisir un modèle → vérifier les prérequis → télécharger volontairement → démarrer un chat local**.

Nous avons développé :

| Domaine | Fonctionnalités de Heretic Studio |
| --- | --- |
| **Ergonomie et interface** | Tableau de bord français, barre latérale fixe sur ordinateur, navigation par tâches, parcours en trois étapes, états explicites, affichage adaptatif, focus clavier et rendu Markdown limité à un sous-ensemble sûr. |
| **Diagnostic du matériel** | Informations système, RAM, stockage, GPU NVIDIA détectés via `nvidia-smi`. |
| **Estimation de compatibilité** | Estimations **indicatives** de RAM/VRAM/disque selon le modèle et la précision ; elles **ne certifient pas** qu'un modèle fonctionnera. |
| **Logiciels IA** | Analyse de versions Python, PyTorch et des bibliothèques utiles ; vérification facultative de CUDA ou Apple MPS. |
| **Catalogue** | Quelques modèles Qwen, Llama, Gemma et Mistral ; consultation des métadonnées publiques Hugging Face. |
| **Téléchargement contrôlé** | Vérification préalable de la taille et de l'espace disque, acceptation explicite des conditions, progression, annulation et contrôle de la révision. |
| **Chat local** | Chargement volontaire d'un modèle téléchargé et validé dans un processus séparé ; conversation sur GPU NVIDIA/CUDA ou CPU, arrêt manuel. |
| **Qualité et performances** | Styles de réponses (concis, standard, pédagogique), limite réglable de 128 à 512 nouveaux tokens, alerte de troncature, tokens/s, durée, RAM du processus et allocations PyTorch CUDA. |
| **Récupération ciblée** | Vérification **hors ligne** des fichiers Qwen2.5-0.5B-Instruct déjà transférés, avant de finaliser un téléchargement interrompu. |

**Ce qui n'est pas encore disponible dans Studio :** exécution des routines d'abliteration Heretic, optimisation automatisée, export de modèles modifiés, comparaison automatique de leur exactitude, installation « un clic », mode multiutilisateur ou hébergement cloud. Ces capacités ne doivent pas être déduites de la présence du moteur d'origine dans le dépôt.

### Prérequis

- **Ordinateur Windows, Linux ou macOS** ; Studio s'ouvre dans un navigateur **sur cet ordinateur**.
- **Git**, **Python 3.10+** et **Node.js 20.19+** (avec npm). Python **3.11 ou 3.12** constitue un choix simple pour les dépendances IA ; d'autres versions peuvent fonctionner si leurs paquets sont compatibles.
- Une connexion Internet pour la **première installation des dépendances**, la recherche Hugging Face et le téléchargement des poids. Une conversation avec un modèle **déjà installé** n'utilise pas d'API de génération en ligne.
- **Facultatif pour le chat :** PyTorch, Transformers, Accelerate, safetensors et sentencepiece ; un build PyTorch/CUDA compatible avec le matériel est nécessaire pour utiliser une carte NVIDIA.
- De la place sur le disque et un forfait de données suffisant. **PyTorch avec CUDA et les poids d'un modèle peuvent représenter plusieurs gigaoctets**. Vérifier leur taille avant toute installation, surtout avec une connexion limitée.

> [!IMPORTANT]
> **Le diagnostic et le catalogue ne nécessitent pas de télécharger un modèle ni d'installer PyTorch.** N'installez les dépendances lourdes d'inférence que si vous souhaitez réellement charger un modèle. Pour CUDA, choisir d'abord la commande correspondant à votre matériel sur [le site officiel de PyTorch](https://pytorch.org/get-started/locally/) ; ne pas supposer qu'une installation Python standard fournit le bon build GPU.

### Installation rapide — Windows (PowerShell / VS Code)

Les commandes suivantes concernent **Heretic Studio**, pas le programme `heretic` de la section [Usage](#usage).

**1. Cloner notre branche expérimentale** (première installation) :

~~~powershell
git clone --branch feature/heretic-studio-local-chat https://github.com/YakeDev/heretic.git
cd heretic
~~~

Si vous avez **déjà cloné** le dépôt et que vous êtes sur cette branche :

~~~powershell
git pull --ff-only origin feature/heretic-studio-local-chat
~~~

Si vous avez cloné la branche `master` et souhaitez changer de branche, vérifiez d'abord que vous n'avez **aucune modification locale non enregistrée**, puis :

~~~powershell
git fetch origin
git switch --track origin/feature/heretic-studio-local-chat
~~~

**2. Démarrer le backend Python** dans un **premier terminal** depuis la racine du dépôt :

~~~powershell
cd studio\backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8765
~~~

Un contrôle rapide doit répondre sur **http://127.0.0.1:8765/api/health**.

> La racine `http://127.0.0.1:8765/` peut afficher **404 Not Found** : c'est normal. Ce port héberge l'API, **pas** l'interface graphique. Le backend doit rester ouvert pendant l'utilisation de Studio.

**3. Démarrer le frontend** dans un **deuxième terminal** :

~~~powershell
cd studio\frontend
npm install
npm run dev
~~~

Ces deux commandes supposent que ce deuxième terminal est ouvert à la racine du dépôt. Ouvrir ensuite **http://127.0.0.1:5173** dans Chrome, Firefox ou Edge. Conserver les **deux terminaux ouverts**.

#### Installation facultative pour utiliser le chat IA

Dans le **premier terminal**, arrêtez le backend avec `Ctrl+C`, puis, depuis `studio\backend` :

~~~powershell
# Si nécessaire, installer d'abord un PyTorch compatible avec le GPU :
# https://pytorch.org/get-started/locally/
.\.venv\Scripts\python.exe -m pip install -r requirements-inference.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8765
~~~

Le fichier `requirements-inference.txt` contient **PyTorch et d'autres dépendances**. Si vous utilisez CUDA, installez **d'abord** le build PyTorch approprié selon la documentation officielle ; l'installation des autres dépendances doit conserver cette version compatible. Cette étape **peut nécessiter un téléchargement volumineux**.

### Installation — Linux / macOS

Depuis un terminal :

~~~bash
git clone --branch feature/heretic-studio-local-chat https://github.com/YakeDev/heretic.git
cd heretic/studio/backend
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8765
~~~

Dans un **autre terminal**, depuis la racine du dépôt :

~~~bash
cd heretic/studio/frontend
npm install
npm run dev
~~~

Ouvrir **http://127.0.0.1:5173**. Pour le chat local, installer les dépendances depuis `studio/backend/requirements-inference.txt` avec le Python de l'environnement virtuel, en choisissant le build PyTorch adapté à la plateforme. Le chat **CPU** peut être lent ; la détection NVIDIA et CUDA n'est pas applicable à tous les ordinateurs.

### Premiers pas dans l'interface

1. **Vue d'ensemble / Mon matériel** : consulter RAM, GPU et stockage. Les résultats sont informatifs.
2. **Modèles IA** : choisir par exemple `Qwen/Qwen2.5-0.5B-Instruct`, un petit modèle adapté aux premiers essais. La sélection ne déclenche aucun téléchargement.
3. **Compatibilité / Logiciels IA** : évaluer les ressources et vérifier les bibliothèques installées. Une estimation favorable **n'est pas une garantie**.
4. **Télécharger** : cliquer sur la vérification de taille et de stockage, consulter la licence officielle, confirmer les conditions **uniquement si elles sont acceptées**, puis lancer le téléchargement. Ne pas confondre vérification et téléchargement effectif.
5. **Chat local** : cliquer sur **Actualiser les modèles téléchargés**, sélectionner un snapshot local terminé, choisir **GPU NVIDIA (CUDA)** ou **CPU**, puis **Charger le modèle**.
6. Attendre l'état **« Modèle prêt à répondre »** (ou `ready`), saisir une question, par exemple « Explique TCP et UDP en trois phrases », puis cliquer sur **Envoyer le message**.
7. Au besoin, personnaliser le **style** et la **longueur maximale** ; consulter les métriques sous la réponse. Cliquer sur **Arrêter le modèle** pour libérer les ressources.

> **À propos de la qualité des réponses :** le test réel du petit Qwen2.5-0.5B-Instruct a confirmé une génération locale, mais également des **erreurs factuelles** sur TCP/UDP. L'interface ne peut pas corriger automatiquement les connaissances d'un modèle. Vérifier les informations importantes auprès de sources fiables.

### Où sont enregistrés les fichiers ?

Les poids téléchargés par Studio sont rangés dans le profil utilisateur :

| Système | Emplacement habituel |
| --- | --- |
| Windows | `%USERPROFILE%\.cache\heretic-studio\models` |
| Linux/macOS | `~/.cache/heretic-studio/models/` |

Un modèle ne figure dans le chat que si Studio reconnaît son **snapshot terminé**. La présence seule de `model.safetensors` ne suffit pas.

**Téléchargement Qwen interrompu ?** Ne recommencez pas immédiatement un téléchargement important. La procédure de [récupération hors ligne de Qwen2.5-0.5B](studio/README.md#récupérer-le-téléchargement-interrompu-de-qwen25-05b-sans-internet) permet de vérifier les empreintes des fichiers existants ; elle reste **spécifique à cette version de Qwen** et n'est pas une fonction générale de reprise automatique.

### Dépannage courant

| Symptôme | Vérification / action |
| --- | --- |
| `127.0.0.1:8765/` affiche `404` | Normal : utiliser `127.0.0.1:8765/api/health` pour l'API et `127.0.0.1:5173` pour le site. |
| **Backend indisponible** | Vérifier le terminal Python, le port `8765` et l'URL locale. |
| `pip` ou `python` non reconnu dans PowerShell | Utiliser le Python de `.venv` via `.\.venv\Scripts\python.exe -m pip ...`, ou vérifier l'installation de Python. |
| **PyTorch absent / CUDA indisponible** | Installer explicitement les dépendances facultatives et vérifier le build PyTorch ainsi que le pilote NVIDIA. Le diagnostic CUDA n'est pas une preuve de compatibilité du modèle. |
| **Aucun modèle disponible dans le chat** | Vérifier que le téléchargement a été **terminé et validé**, puis actualiser la liste du chat. |
| **Chargement ou génération échoué** | Lire l'étape d'erreur affichée, essayer un modèle moins exigeant ou le mode CPU ; vérifier la mémoire disponible. Ne pas retélécharger les poids par réflexe. |
| **Réponse tronquée ou erronée** | Augmenter la limite de tokens si nécessaire et vérifier le contenu : un petit modèle peut donner des réponses incorrectes même si son exécution est réussie. |
| **Forfait Internet limité** | Lire la taille estimée avant confirmation et éviter les installations CUDA ou les poids volumineux sans connexion adaptée. |

### Sécurité, confidentialité et limites

- **Serveur local uniquement** : démarrer Uvicorn avec `--host 127.0.0.1` ; **ne pas exposer le port 8765 sur Internet ou un réseau public**. L'alpha n'est pas une application cloud ni un serveur sécurisé multiutilisateur.
- L'inférence utilise des **poids safetensors**, avec `local_files_only=True` et `trust_remote_code=False`. Ce sont des mesures de précaution, **pas une garantie absolue contre tout fichier malveillant**.
- Les téléchargements sont limités aux modèles autorisés par le catalogue et nécessitent une **confirmation de licence** ; les formats de poids Python/pickle ne sont pas acceptés par le gestionnaire.
- La **recherche de modèles** et le **téléchargement des poids** communiquent avec Hugging Face ; la **génération de texte**, une fois le modèle installé, s'effectue sur la machine.
- L'historique du chat est géré localement dans cette alpha, sans espace utilisateur en ligne. Des fichiers d'état temporaires peuvent subsister en cas de panne ; ne pas utiliser ce prototype pour des données hautement sensibles.
- **Une seule session de modèle et une génération à la fois** sont prises en charge. La présence d'une architecture dans le catalogue ne garantit pas son exécution ; Gemma 3 n'est pas encore autorisé dans le chat local.
- **Les modèles Llama** peuvent nécessiter d'accepter la licence Meta et d'obtenir une autorisation d'accès. Chaque utilisateur demeure responsable de respecter la licence de ses modèles.
- La future utilisation de Heretic pour modifier des modèles **n'est pas activée par l'interface Studio**.

### Tester, contribuer et suivre le développement

Dans `studio/backend`, après installation de `requirements-dev.txt` :

~~~bash
python -m unittest discover -s tests -v
~~~

Dans `studio/frontend` :

~~~bash
npm run build
~~~

Ces commandes contrôlent le code, mais **ne remplacent pas un essai réel sur un GPU**, ni une recette UX/accessibilité avec des utilisateurs.

- [Documentation technique de Studio](studio/README.md)
- [Principes UX/UI et scénarios de recette](studio/UX_UI_GUIDELINES.md)
- [Branche de développement de Studio](https://github.com/YakeDev/heretic/tree/feature/heretic-studio-local-chat)
- [PR de travail Heretic Studio](https://github.com/YakeDev/heretic/pull/6)

**Crédits :** Heretic Studio est une extension expérimentale de ce fork. Le moteur Heretic, sa recherche et sa documentation d'origine appartiennent à leurs auteurs et contributeurs, notamment Philipp Emanuel Weidmann. Nous conservons le code et l'attribution amont, ainsi que la licence **AGPL-3.0-or-later** du dépôt. Voir [License](#license) et [Citation](#citation) pour le projet original.


## Usage

Prepare a Python 3.10+ environment with PyTorch 2.2+ installed as appropriate
for your hardware. Then run:

```sh
pip install -U heretic-llm
heretic Qwen/Qwen3-4B-Instruct-2507
```

Replace `Qwen/Qwen3-4B-Instruct-2507` with whatever model you want to decensor.

> [!IMPORTANT]
>
> While PyTorch 2.2 is the minimum version of PyTorch needed for Heretic to work,
> some models and configurations might require features only found in
> later versions. For example, loading MXFP4-quantized models like gpt-oss
> uses `torch.accelerator`, which was added in PyTorch 2.6.

> [!TIP]
>
> Heretic uses [uv](https://docs.astral.sh/uv/) for dependency management,
> and the repository includes a `uv.lock` file pinning every package version.
> If you already use uv (and you probably should!), you can just clone the repo
> and run Heretic with `uv run heretic`, which ensures that your dependencies
> match those used by the developers, improving reliability and security.

The process is fully automatic and does not require configuration; however,
Heretic has a variety of configuration parameters that can be changed for
greater control. Run `heretic --help` to see available command-line options,
or look at [`config.default.toml`](config.default.toml) if you prefer to use
a configuration file.

At the start of a program run, Heretic benchmarks the system to determine
the optimal batch size to make the most of the available hardware.
On an RTX 3090, with the default configuration, decensoring
[Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
takes about 20-30 minutes. Note that Heretic supports model quantization with
bitsandbytes, which can drastically reduce the amount of VRAM required to process
models. Set the `quantization` option to `bnb_4bit` to enable quantization.

After Heretic has finished decensoring a model, you are given the option to
save the model, upload it to Hugging Face, chat with it to test how well it works,
run standard benchmarks on it, or any combination of those actions.


## How Heretic works

Heretic implements a parametrized variant of directional ablation. For each
supported transformer component (currently, attention out-projection and
MLP down-projection), it identifies the associated matrices in each transformer
layer, and orthogonalizes them with respect to the relevant "residual direction",
inhibiting the expression of that direction in the result of multiplications
with that matrix.

Residual directions are computed for each layer as a difference-of-means between
the first-token residuals for "harmful" and "harmless" example prompts.

The ablation process is controlled by several optimizable parameters:

* `direction_index`: Either the index of a residual direction, or the special
  value `per layer`, indicating that each layer should be ablated using the
  residual direction associated with that layer.
* `max_weight`, `max_weight_position`, `min_weight`, and `min_weight_distance`:
  For each component, these parameters describe the shape and position of the
  ablation weight kernel over the layers. The following diagram illustrates this:

<img width="800" height="500" alt="Explanation" src="https://github.com/user-attachments/assets/82e4b84e-5a82-4faf-b918-ac642f9e4892" />

&nbsp;

Heretic's main innovations over existing abliteration systems are:

* The shape of the ablation weight kernel is highly flexible, which, combined with
  automatic parameter optimization, can improve the compliance/quality tradeoff.
  Non-constant ablation weights were previously explored by Maxime Labonne in
  [gemma-3-12b-it-abliterated-v2](https://huggingface.co/mlabonne/gemma-3-12b-it-abliterated-v2).
* The residual direction index is a float rather than an integer. For non-integral
  values, the two nearest residual direction vectors are linearly interpolated.
  This unlocks a vast space of additional directions beyond the ones identified
  by the difference-of-means computation, and often enables the optimization
  process to find a better direction than that belonging to any individual layer.
* Ablation parameters are chosen separately for each component. I have found that
  MLP interventions tend to be more damaging to the model than attention interventions,
  so using different ablation weights can squeeze out some extra performance.


## Prior art

I'm aware of the following publicly available implementations of abliteration
techniques:

* [AutoAbliteration](https://huggingface.co/posts/mlabonne/714992455492422)
* [abliterator.py](https://github.com/FailSpy/abliterator)
* [wassname's Abliterator](https://github.com/wassname/abliterator)
* [ErisForge](https://github.com/Tsadoq/ErisForge)
* [Removing refusals with HF Transformers](https://github.com/Sumandora/remove-refusals-with-transformers)
* [deccp](https://github.com/AUGMXNT/deccp)

Note that Heretic was written from scratch, and does not reuse code from
any of those projects.


## Acknowledgments

The development of Heretic was informed by:

* [The original abliteration paper (Arditi et al. 2024)](https://arxiv.org/abs/2406.11717)
* [Maxime Labonne's article on abliteration](https://huggingface.co/blog/mlabonne/abliteration),
  as well as some details from the model cards of his own abliterated models (see above)
* Jim Lai's articles describing ["projected abliteration"](https://huggingface.co/blog/grimjim/projected-abliteration)
  and ["norm-preserving biprojected abliteration"](https://huggingface.co/blog/grimjim/norm-preserving-biprojected-abliteration)


## Citation

If you use Heretic for your research, please cite it using the following BibTeX entry:

```bibtex
@misc{heretic,
  author = {Weidmann, Philipp Emanuel},
  title = {Heretic: Fully automatic censorship removal for language models},
  year = {2025},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/p-e-w/heretic}}
}
```


## License

Copyright &copy; 2025-2026  Philipp Emanuel Weidmann (<pew@worldwidemann.com>) + contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

**By contributing to this project, you agree to release your
contributions under the same license.**
