import { useEffect, useState } from 'react';

type SystemInfo = {
  os: string;
  cpu: string;
  logical_cpus: number | null;
  ram_total_gb: number;
  ram_available_gb: number;
  nvidia_gpus: { name: string; memory_total_gb: number; memory_free_gb: number }[];
  gpu_detection_note: string;
};

type ProjectInfo = { name: string; version: string; python: string; mode: string };

const API_BASE = 'http://127.0.0.1:8765';

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(API_BASE + path, { signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.json() as Promise<T>;
}

export function App() {
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setLoading(true);
    setError('');
    try {
      const [s, p] = await Promise.all([
        getJson<SystemInfo>('/api/system'),
        getJson<ProjectInfo>('/api/project'),
      ]);
      setSystem(s);
      setProject(p);
    } catch {
      setSystem(null);
      setProject(null);
      setError('Connexion impossible. Démarre le backend local sur 127.0.0.1:8765, puis réessaie.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">H</span><div><strong>HERETIC</strong><small>STUDIO <span>ALPHA</span></small></div></div>
        <div className="nav-title">ESPACE DE TRAVAIL</div>
        <nav aria-label="Navigation principale">
          <a className="nav-item active" href="#overview"><span>◫</span> Vue d'ensemble</a>
          <a className="nav-item" href="#machine"><span>▤</span> Mon matériel</a>
          <a className="nav-item" href="#roadmap"><span>◇</span> Prochaines étapes</a>
        </nav>
        <div className="sidebar-bottom"><div className="status-dot" /> Mode local · Lecture seule</div>
      </aside>
      <main>
        <header className="topbar"><span>LABORATOIRE / TABLEAU DE BORD</span><span className="topbar-badge">Aucune expérience en cours</span></header>
        <div className="content" id="overview">
          <div className="eyebrow">BIENVENUE DANS TON LABORATOIRE</div>
          <h1>Comprendre tes modèles.<br /><em>Maîtriser tes expériences.</em></h1>
          <p className="intro">Heretic Studio rend l'environnement Heretic plus accessible. Cette première version affiche seulement des diagnostics locaux : aucun modèle n'est modifié.</p>
          {error && <div role="alert" className="error"><strong>Backend indisponible</strong><p>{error}</p></div>}
          <div className="section-heading" id="machine"><div><span className="eyebrow">01 / DIAGNOSTIC</span><h2>Ton environnement de travail</h2></div><button onClick={() => void refresh()} disabled={loading}>{loading ? 'Analyse...' : '↻ Actualiser'}</button></div>
          <div className="grid">
            <article className="card"><div className="card-icon">▣</div><div className="label">SYSTÈME</div><div className="value">{system?.os ?? '—'}</div><div className="sub">{system?.cpu ?? 'En attente du backend'}</div></article>
            <article className="card"><div className="card-icon">▥</div><div className="label">MÉMOIRE RAM</div><div className="value">{system ? String(system.ram_total_gb) + ' Go' : '—'}</div><div className="sub">{system ? String(system.ram_available_gb) + ' Go disponibles' : 'Informations indisponibles'}</div></article>
            <article className="card"><div className="card-icon">◈</div><div className="label">GPU NVIDIA DÉTECTÉ</div><div className="value">{system ? system.nvidia_gpus.length : '—'}</div><div className="sub">{system?.nvidia_gpus.map((gpu) => gpu.name + ' · ' + gpu.memory_total_gb + ' Go VRAM').join(' ; ') || 'Non détecté ou non pris en charge par cette sonde'}</div></article>
          </div>
          {system && <div className="note">ⓘ {system.gpu_detection_note} Ce diagnostic ne valide pas la compatibilité avec un modèle.</div>}
          <div className="panel-grid">
            <article className="panel"><span className="eyebrow">02 / MOTEUR</span><h2>Heretic</h2><p>Informations lues depuis le projet Python existant.</p><dl><div><dt>Paquet</dt><dd>{project?.name ?? '—'}</dd></div><div><dt>Version du code</dt><dd>{project?.version ?? '—'}</dd></div><div><dt>Python requis</dt><dd>{project?.python ?? '—'}</dd></div></dl></article>
            <article className="panel" id="roadmap"><span className="eyebrow">03 / À VENIR</span><h2>Expérimentations</h2><p>L'exécution et la modification de modèles seront ajoutées après validation du moteur, des ressources et des mécanismes d'arrêt.</p><div className="coming"><span>Catalogue des modèles</span><b>À venir</b></div><div className="coming"><span>Assistant de configuration</span><b>À venir</b></div><div className="coming"><span>Comparaison des résultats</span><b>À venir</b></div></article>
          </div>
          <footer>HERETIC STUDIO · VERSION EXPÉRIMENTALE · AUCUNE ACTION SUR LES MODÈLES</footer>
        </div>
      </main>
    </div>
  );
}
