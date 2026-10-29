import { useEffect, useRef, useState } from 'react';

type Preview = {
  plan_id: string;
  model_id: string;
  revision: string;
  file_count: number;
  total_bytes: number;
  disk_free_bytes: number;
  gated: boolean;
  destination: string;
  expires_in_seconds: number;
  warning: string;
};

type Status = {
  job_id: string;
  model_id: string;
  revision: string;
  destination: string;
  state: 'downloading' | 'completed' | 'failed' | 'canceled';
  completed_files?: number;
  total_files?: number;
  completed_bytes?: number;
  total_bytes?: number;
  message?: string;
};

const API = 'http://127.0.0.1:8765';
const gb = (bytes: number) => (bytes / 1024 ** 3).toFixed(2) + ' Gio';

export function DownloadManager({ modelId }: { modelId: string }) {
  const token = useRef<string>('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [job, setJob] = useState<Status | null>(null);
  const [jobId, setJobId] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setPreview(null);
    setAccepted(false);
    setError('');
  }, [modelId]);

  async function sessionToken() {
    if (token.current) return token.current;
    const response = await fetch(API + '/api/downloads/session', {
      signal: AbortSignal.timeout(8000),
    });
    if (!response.ok) throw new Error('Session indisponible');
    const body = await response.json() as { token: string };
    token.current = body.token;
    return token.current;
  }

  async function request<T>(path: string, body?: object): Promise<T> {
    const auth = await sessionToken();
    const response = await fetch(API + path, {
      method: body ? 'POST' : 'GET',
      headers: { 'X-Heretic-Token': auth, ...(body ? { 'Content-Type': 'application/json' } : {}) },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(body ? 30000 : 8000),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({})) as { detail?: string };
      throw new Error(data.detail || 'Erreur HTTP ' + response.status);
    }
    return await response.json() as T;
  }

  async function prepare() {
    if (!modelId) return;
    setBusy(true);
    setError('');
    setAccepted(false);
    setPreview(null);
    try {
      const data = await request<Preview>('/api/downloads/preview', { model_id: modelId });
      setPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Préparation indisponible');
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    if (!preview || !accepted) return;
    setBusy(true);
    setError('');
    try {
      const result = await request<{ job_id: string; state: 'downloading'; model_id: string }>(
        '/api/downloads/start',
        { plan_id: preview.plan_id, license_accepted: true },
      );
      setJobId(result.job_id);
      setJob({
        job_id: result.job_id,
        model_id: result.model_id,
        revision: preview.revision,
        destination: preview.destination,
        state: 'downloading',
        completed_bytes: 0,
        total_bytes: preview.total_bytes,
        completed_files: 0,
        total_files: preview.file_count,
      });
      setPreview(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Téléchargement impossible');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!jobId) return;
    let running = true;
    async function poll() {
      try {
        const result = await request<Status>('/api/downloads/' + jobId);
        if (running) setJob(result);
      } catch {
        if (running) setError('Progression indisponible : vérifie le backend local.');
      }
    }
    void poll();
    const timer = window.setInterval(() => {
      if (job?.state === 'downloading') void poll();
    }, 2000);
    return () => { running = false; window.clearInterval(timer); };
    // The interval is replaced when the state changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, job?.state]);

  async function cancel() {
    if (!jobId) return;
    setBusy(true);
    setError('');
    try {
      const result = await request<{ state: 'canceled' }>(
        '/api/downloads/' + jobId + '/cancel', {},
      );
      setJob((previous) => previous ? { ...previous, state: result.state } : previous);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Annulation impossible');
    } finally {
      setBusy(false);
    }
  }

  const progress = job?.total_bytes && job.completed_bytes !== undefined
    ? Math.min(100, Math.round(job.completed_bytes / job.total_bytes * 100))
    : 0;
  const inProgress = job?.state === 'downloading';
  return (
    <section className="download-panel" id="downloads" aria-labelledby="downloads-title">
      <span className="eyebrow">05 / TÉLÉCHARGEMENT LOCAL</span>
      <h3 id="downloads-title">Télécharger les fichiers du modèle</h3>
      <p>
        Téléchargement facultatif, uniquement sur ton ordinateur. Le modèle ne sera ni
        exécuté ni modifié. Pour une conversation, il faudra encore ajouter le module d'inférence.
      </p>
      <div className="selected-model">
        <span>MODÈLE CHOISI DANS LE CATALOGUE</span>
        <strong>{modelId || 'Sélectionne un modèle ci-dessus.'}</strong>
      </div>
      <button type="button" onClick={() => void prepare()} disabled={!modelId || busy || inProgress}>
        {busy && !inProgress ? 'Préparation…' : 'Vérifier les fichiers et le stockage'}
      </button>
      {preview && (
        <div className="download-review">
          <h4>Vérification avant téléchargement</h4>
          <dl>
            <div><dt>Modèle</dt><dd>{preview.model_id}</dd></div>
            <div><dt>Fichiers autorisés</dt><dd>{preview.file_count}</dd></div>
            <div><dt>Taille estimée</dt><dd>{gb(preview.total_bytes)}</dd></div>
            <div><dt>Espace libre détecté</dt><dd>{gb(preview.disk_free_bytes)}</dd></div>
            <div><dt>Accès contrôlé</dt><dd>{preview.gated ? 'Oui, autorisation nécessaire' : 'Non signalé'}</dd></div>
            <div><dt>Révision vérifiée</dt><dd className="code">{preview.revision.slice(0, 12)}…</dd></div>
          </dl>
          <p>{preview.warning}</p>
          <a
            href={'https://huggingface.co/' + preview.model_id}
            target="_blank"
            rel="noopener noreferrer"
            className="model-link"
          >
            Consulter la licence et les conditions ↗
          </a>
          <label className="license-check">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(event) => setAccepted(event.target.checked)}
            />
            J'ai consulté les conditions et je confirme avoir le droit de télécharger ce modèle.
          </label>
          <button type="button" onClick={() => void start()} disabled={!accepted || busy}>
            Confirmer le téléchargement
          </button>
        </div>
      )}
      {error && <p role="alert" className="error">{error}</p>}
      {job && (
        <div className="download-progress" aria-live="polite">
          <strong>
            {job.state === 'downloading' && 'Téléchargement en cours'}
            {job.state === 'completed' && 'Fichiers téléchargés'}
            {job.state === 'failed' && 'Téléchargement échoué'}
            {job.state === 'canceled' && 'Téléchargement annulé'}
          </strong>
          <p>{job.model_id}</p>
          <progress value={progress} max="100">{progress}%</progress>
          <span>{progress}% des fichiers entièrement transférés · {job.completed_files ?? 0}/{job.total_files ?? '?'} fichiers</span>
          {job.message && <p>{job.message}</p>}
          {job.state === 'completed' && <p className="download-path">Dossier : {job.destination}</p>}
          {inProgress && (
            <button type="button" onClick={() => void cancel()} disabled={busy}>
              Annuler le téléchargement
            </button>
          )}
        </div>
      )}
      <p className="download-caution">
        Les formats Python et pickle/bin sont exclus. Le premier téléchargement peut utiliser
        beaucoup de données internet ; la progression est comptée par fichier terminé.
      </p>
    </section>
  );
}
