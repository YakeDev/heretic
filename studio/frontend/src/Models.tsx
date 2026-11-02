import { useEffect, useState, type FormEvent } from 'react';
import { DownloadManager } from './DownloadManager';
import { HardwareEstimator } from './HardwareEstimator';
import { LocalChat } from './LocalChat';
import { SoftwareDiagnostics } from './SoftwareDiagnostics';

type CuratedModel = {
  id: string;
  family: string;
  parameters: string;
  description: string;
  access: string;
  url: string;
  compatibility: string;
};

type HubModel = {
  id: string;
  url: string;
  gated: boolean;
  task: string | null;
  downloads: number | null;
  likes: number | null;
};

const API_BASE = 'http://127.0.0.1:8765';

export function Models() {
  const [catalog, setCatalog] = useState<CuratedModel[]>([]);
  const [catalogError, setCatalogError] = useState('');
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<HubModel[]>([]);
  const [searchStatus, setSearchStatus] = useState('');
  const [searching, setSearching] = useState(false);
  // This is a non-sensitive UI preference; it does not download or execute a model.
  const [selectedModel, setSelectedModel] = useState(() => {
    try {
      return window.sessionStorage.getItem('heretic-studio-selected-model') ?? '';
    } catch {
      return '';
    }
  });

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await fetch(API_BASE + '/api/models', { signal: controller.signal });
        if (!response.ok) throw new Error('API inaccessible');
        const body = await response.json() as { models: CuratedModel[] };
        if (!controller.signal.aborted) {
          setCatalog(body.models);
          setSelectedModel((previous) => {
            if (previous && !body.models.some((model) => model.id === previous)) {
              try { window.sessionStorage.removeItem('heretic-studio-selected-model'); } catch { /* optional storage */ }
              return '';
            }
            return previous;
          });
        }
      } catch {
        if (!controller.signal.aborted) setCatalogError('Impossible de charger le catalogue local.');
      } finally {
        if (!controller.signal.aborted) setLoadingCatalog(false);
      }
    })();
    return () => controller.abort();
  }, []);

  function selectModel(id: string) {
    setSelectedModel(id);
    try { window.sessionStorage.setItem('heretic-studio-selected-model', id); } catch { /* storage not required */ }
  }

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = query.trim();
    if (!/^[A-Za-z0-9_. /-]{2,64}$/.test(value)) {
      setSearchStatus('Saisis 2 à 64 caractères : lettres, chiffres, espaces, point, tiret ou barre oblique.');
      setResults([]);
      return;
    }
    setSearching(true);
    setResults([]);
    setSearchStatus('');
    try {
      const response = await fetch(
        API_BASE + '/api/models/search?q=' + encodeURIComponent(value),
        { signal: AbortSignal.timeout(8000) },
      );
      if (!response.ok) throw new Error('Service indisponible');
      const body = await response.json() as { models: HubModel[] };
      setResults(body.models);
      setSearchStatus(
        body.models.length === 0
          ? 'Aucun résultat dans les métadonnées publiques.'
          : body.models.length + ' résultat(s) trouvé(s).',
      );
    } catch {
      setSearchStatus('Recherche impossible. Vérifie la connexion et le backend local.');
    } finally {
      setSearching(false);
    }
  }

  return (
    <section className="models-section" id="models" aria-labelledby="models-title">
      <div className="section-heading">
        <div>
          <span className="eyebrow">02 / BIBLIOTHÈQUE</span>
          <h2 id="models-title">Choisir un modèle IA</h2>
        </div>
        <span className="readonly-badge">Expérimental · Téléchargement sur confirmation</span>
      </div>
      <p className="model-intro">Sélectionne un modèle pour évaluer ton matériel et, si tu le souhaites, préparer son téléchargement. La sélection ne lance aucune opération.</p>
      {catalogError && <p className="error" role="alert">{catalogError}</p>}
      {loadingCatalog ? <p className="sub" role="status">Chargement du catalogue local…</p> : (
        <div className="model-grid">
          {catalog.map((model) => (
            <article className={'model-card' + (selectedModel === model.id ? ' is-selected' : '')} key={model.id}>
              <div className="model-card-top">
                <span className="model-family">{model.family}</span>
                <span className="model-params">{model.parameters}</span>
              </div>
              <h3>{model.id.split('/').at(-1)}</h3>
              <p>{model.description}</p>
              <div className="model-meta">Accès : {model.access}</div>
              <div className="model-meta">Compatibilité Heretic : non vérifiée</div>
              <button
                type="button"
                className="model-check"
                onClick={() => selectModel(model.id)}
                aria-pressed={selectedModel === model.id}
              >
                {selectedModel === model.id ? 'Modèle sélectionné ✓' : 'Choisir ce modèle'}
              </button>
              <a href={model.url} target="_blank" rel="noopener noreferrer" className="model-link">
                Voir sur Hugging Face <span aria-hidden="true">↗</span>
              </a>
            </article>
          ))}
        </div>
      )}
      {selectedModel ? (
        <div className="model-selection-next" role="status">
          <strong>Modèle sélectionné : {selectedModel}</strong>
          <a href="#compatibility">Vérifier les ressources ↗</a>
          <a href="#downloads">Préparer le téléchargement ↗</a>
        </div>
      ) : (
        <p className="model-helper">Choisis un modèle dans le catalogue avant de vérifier sa compatibilité.</p>
      )}
      <div className="hub-panel">
        <div>
          <span className="eyebrow">RECHERCHE EXTERNE</span>
          <h3>Rechercher sur Hugging Face</h3>
          <p>Recherche des métadonnées publiques. Aucun téléchargement, aucune exécution, aucune connexion à un compte.</p>
        </div>
        <form className="hub-search" onSubmit={(event) => void search(event)}>
          <label htmlFor="hub-query">Nom du modèle ou famille</label>
          <div className="hub-search-row">
            <input
              id="hub-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              maxLength={64}
              autoComplete="off"
              placeholder="Ex. llama, Qwen3, Gemma"
            />
            <button type="submit" disabled={searching}>{searching ? 'Recherche…' : 'Rechercher'}</button>
          </div>
        </form>
        {searchStatus && <p role="status" className="search-status">{searchStatus}</p>}
        {results.length > 0 && (
          <div className="results-list" aria-label="Résultats Hugging Face">
            {results.map((model) => (
              <div className="hub-result" key={model.id}>
                <div className="hub-result-text">
                  <strong>{model.id}</strong>
                  <span>
                    {model.gated ? 'Accès contrôlé' : 'Accès à vérifier'}
                    {' · '}{model.task ?? 'Tâche non précisée'}
                    {model.downloads !== null ? ' · ' + new Intl.NumberFormat('fr-FR').format(model.downloads) + ' téléchargements' : ''}
                  </span>
                </div>
                <a href={model.url} target="_blank" rel="noopener noreferrer" className="model-link">Voir ↗</a>
              </div>
            ))}
          </div>
        )}
      </div>
      <p className="model-license-note">Certains modèles (notamment Llama) nécessitent une licence ou une autorisation. Vérifie toujours la fiche officielle avant téléchargement.</p>
      <HardwareEstimator modelId={selectedModel} />
      <SoftwareDiagnostics />
      <DownloadManager modelId={selectedModel} />
      <LocalChat />
    </section>
  );
}
