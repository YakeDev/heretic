import { useState } from 'react';

type Package = { package: string; label: string; version: string | null };

type Runtime = {
  status: 'checked' | 'timeout' | 'probe_failed' | 'torch_not_installed';
  cuda_available?: boolean;
  mps_available?: boolean;
  cuda_devices?: number;
  cuda_build?: string | null;
  rocm_build?: string | null;
};

type Nvidia = {
  status: 'detected' | 'not_detected' | 'probe_failed';
  gpus?: { name: string; driver_version: string; memory_total_gib: number }[];
};

type SoftwareInfo = {
  python_version: string;
  python_executable: string;
  platform: string;
  packages: Package[];
  driver_nvidia: Nvidia;
  torch_runtime: Runtime;
  notes: string[];
  compatibility: 'not_verified';
  read_only: true;
};

function runtimeLabel(runtime: Runtime): string {
  switch (runtime.status) {
    case 'checked':
      return 'Sonde exécutée';
    case 'torch_not_installed':
      return 'PyTorch absent';
    case 'timeout':
      return 'Délai dépassé';
    case 'probe_failed':
      return 'Sonde indisponible';
  }
}

export function SoftwareDiagnostics() {
  const [info, setInfo] = useState<SoftwareInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function runDiagnostics() {
    setLoading(true);
    setInfo(null);
    setError('');
    try {
      const response = await fetch('http://127.0.0.1:8765/api/hardware/software', {
        signal: AbortSignal.timeout(25000),
      });
      if (!response.ok) throw new Error('Diagnostic inaccessible');
      setInfo(await response.json() as SoftwareInfo);
    } catch {
      setError('Le diagnostic a échoué. Vérifie que le backend local est accessible.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="software-panel" id="software" aria-labelledby="software-title">
      <div className="section-heading">
        <div>
          <span className="eyebrow">04 / ENVIRONNEMENT LOGICIEL</span>
          <h2 id="software-title">Pilotes, Python et bibliothèques IA</h2>
        </div>
        <button type="button" onClick={() => void runDiagnostics()} disabled={loading}>
          {loading ? 'Vérification en cours…' : 'Vérifier mon environnement'}
        </button>
      </div>
      <p className="model-intro">
        Contrôle les versions installées et vérifie si PyTorch détecte CUDA ou Apple MPS.
        Cette action analyse uniquement le Python qui exécute Heretic Studio, sans télécharger de modèle.
      </p>
      <div className="note">
        ⓘ La disponibilité de CUDA n'est pas une preuve de compatibilité de Heretic ou de bitsandbytes.
        Aucune installation ou modification n'est effectuée.
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {info && (
        <div className="software-results" aria-live="polite">
          <div className="hardware-status indeterminate">
            <strong>Compatibilité finale non vérifiée</strong>
            <span>Diagnostic informatif, sans exécution de modèles.</span>
          </div>
          <dl className="software-quickfacts">
            <div><dt>Python</dt><dd>{info.python_version}</dd></div>
            <div><dt>PyTorch</dt><dd>{runtimeLabel(info.torch_runtime)}</dd></div>
            <div><dt>CUDA utilisable par PyTorch</dt><dd>{info.torch_runtime.status !== 'checked' ? 'Inconnu' : info.torch_runtime.cuda_available ? 'Oui (détecté)' : 'Non détecté'}</dd></div>
            <div><dt>Apple MPS utilisable</dt><dd>{info.torch_runtime.status !== 'checked' ? 'Inconnu' : info.torch_runtime.mps_available ? 'Oui (détecté)' : 'Non détecté'}</dd></div>
            <div><dt>Build CUDA / ROCm</dt><dd>{info.torch_runtime.cuda_build ?? '—'} / {info.torch_runtime.rocm_build ?? '—'}</dd></div>
            <div><dt>Pilote NVIDIA</dt><dd>{info.driver_nvidia.gpus?.map((gpu) => gpu.name + ' · ' + gpu.driver_version).join(' ; ') || 'Non vérifié'}</dd></div>
          </dl>
          <h3>Bibliothèques installées</h3>
          <div className="software-packages">
            {info.packages.map((item) => (
              <div key={item.package}>
                <span>{item.label}</span>
                <strong className={item.version === null ? 'not-installed' : ''}>
                  {item.version ?? 'Non installée'}
                </strong>
              </div>
            ))}
          </div>
          <p className="software-environment">
            Environnement examiné : <code>{info.python_executable}</code>
          </p>
          <h3>Limites de ce contrôle</h3>
          <ul className="estimate-warnings">
            {info.notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}
