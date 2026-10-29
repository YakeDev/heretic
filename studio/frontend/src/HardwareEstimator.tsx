import { useEffect, useState, type FormEvent } from 'react';

type Estimate = {
  model_id: string;
  mode: 'inference' | 'optimization';
  precision: 'fp16' | 'bnb_4bit';
  parameters_billions: number;
  weight_memory_gib: number;
  estimated_gpu_gib: number;
  estimated_ram_gib: number;
  estimated_disk_gib: number;
  best_single_nvidia_free_gib: number | null;
  best_single_nvidia_total_gib: number | null;
  status: 'candidate_only' | 'probably_insufficient' | 'indeterminate';
  reasons: string[];
  method: string;
  guaranteed: false;
};

type Props = { modelId: string };

const STATUS_TEXT: Record<Estimate['status'], string> = {
  candidate_only: 'Ressources potentiellement suffisantes',
  probably_insufficient: 'Ressources probablement insuffisantes',
  indeterminate: 'Diagnostic indéterminé',
};

export function HardwareEstimator({ modelId }: Props) {
  const [mode, setMode] = useState<'inference' | 'optimization'>('inference');
  const [precision, setPrecision] = useState<'fp16' | 'bnb_4bit'>('fp16');
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    setEstimate(null);
    setError('');
  }, [modelId]);

  async function check(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!modelId) return;
    setChecking(true);
    setEstimate(null);
    setError('');
    const params = new URLSearchParams({ model_id: modelId, mode, precision });
    try {
      const response = await fetch('http://127.0.0.1:8765/api/hardware/estimate?' + params, {
        signal: AbortSignal.timeout(8000),
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      setEstimate(await response.json() as Estimate);
    } catch {
      setError('Diagnostic indisponible. Vérifie que le backend local est démarré.');
    } finally {
      setChecking(false);
    }
  }

  return (
    <section className="hardware-panel" id="compatibility" aria-labelledby="hardware-title">
      <div className="eyebrow">03 / ESTIMATION MATÉRIELLE</div>
      <h3 id="hardware-title">Mon ordinateur peut-il utiliser ce modèle ?</h3>
      <p>Une première estimation des ressources pour l'inférence ou une expérimentation Heretic. Aucun modèle n'est téléchargé ni chargé.</p>
      <div className="selected-model" aria-live="polite">
        <span>MODÈLE SÉLECTIONNÉ</span>
        <strong>{modelId || 'Sélectionne un modèle dans le catalogue ci-dessus.'}</strong>
      </div>
      <form className="hardware-form" onSubmit={(event) => void check(event)}>
        <label>Utilisation
          <select value={mode} onChange={(event) => { setMode(event.target.value as typeof mode); setEstimate(null); }}>
            <option value="inference">Génération (inférence)</option>
            <option value="optimization">Expérimentation Heretic (optimisation)</option>
          </select>
        </label>
        <label>Précision souhaitée
          <select value={precision} onChange={(event) => { setPrecision(event.target.value as typeof precision); setEstimate(null); }}>
            <option value="fp16">FP16 (16 bits)</option>
            <option value="bnb_4bit">bitsandbytes (4 bits)</option>
          </select>
        </label>
        <button type="submit" disabled={!modelId || checking}>{checking ? 'Évaluation…' : 'Analyser les ressources'}</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {estimate && (
        <div className="estimate-result" aria-live="polite">
          <div className={'hardware-status ' + estimate.status}>
            <strong>{STATUS_TEXT[estimate.status]}</strong>
            <span>Estimation uniquement · Aucune compatibilité garantie</span>
          </div>
          <dl className="estimate-grid">
            <div><dt>GPU / VRAM estimée</dt><dd>{estimate.estimated_gpu_gib} Gio</dd></div>
            <div><dt>RAM indicative</dt><dd>{estimate.estimated_ram_gib} Gio</dd></div>
            <div><dt>Espace disque indicatif</dt><dd>{estimate.estimated_disk_gib} Gio</dd></div>
            <div><dt>VRAM NVIDIA libre détectée</dt><dd>{estimate.best_single_nvidia_free_gib === null ? 'Non détectée' : estimate.best_single_nvidia_free_gib + ' Go'}</dd></div>
          </dl>
          <h4>Points à vérifier</h4>
          <ul className="estimate-warnings">
            {estimate.reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
          <small>Méthode : {estimate.method}. Les estimations sont approximatives et ne constituent pas une mesure réelle.</small>
        </div>
      )}
    </section>
  );
}
