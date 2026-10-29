import { useEffect, useState } from 'react';
import { StudioIcon, type IconName } from './StudioIcon';
import { Models } from './Models';

type SystemInfo = {
  os: string;
  cpu: string;
  logical_cpus: number | null;
  ram_total_gb: number;
  ram_available_gb: number;
  disk_available_gb: number | null;
  architecture: string;
  apple_silicon_possible: boolean;
  nvidia_gpus: { name: string; memory_total_gb: number; memory_free_gb: number }[];
  gpu_detection_note: string;
};

type ProjectInfo = { name: string; version: string; python: string; mode: string };
type NavItem = { id: string; label: string; icon: IconName };
type NavGroup = { label: string; items: NavItem[] };

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'DÉCOUVRIR',
    items: [
      { id: 'overview', label: 'Vue d’ensemble', icon: 'home' },
      { id: 'machine', label: 'Mon matériel', icon: 'cpu' },
      { id: 'models', label: 'Modèles IA', icon: 'layers' },
    ],
  },
  {
    label: 'PRÉPARER',
    items: [
      { id: 'compatibility', label: 'Compatibilité', icon: 'gauge' },
      { id: 'software', label: 'Logiciels IA', icon: 'settings' },
      { id: 'downloads', label: 'Télécharger', icon: 'download' },
    ],
  },
  {
    label: 'EXPÉRIMENTER',
    items: [
      { id: 'local-chat', label: 'Chat local', icon: 'message' },
      { id: 'roadmap', label: 'À venir', icon: 'flask' },
    ],
  },
];

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
  const [activeSection, setActiveSection] = useState('overview');

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
      setError('Le backend local ne répond pas. Lance le serveur Python sur 127.0.0.1:8765, puis réessaie.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  useEffect(() => {
    const allIds = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.id));
    const selectHash = () => {
      const id = decodeURIComponent(window.location.hash.slice(1));
      if (allIds.includes(id)) setActiveSection(id);
    };
    selectHash();
    window.addEventListener('hashchange', selectHash);

    // Anchors include nested panels: use the last heading above the reading
    // line, not an intersection observer that can keep the parent selected.
    let frame = 0;
    const syncActive = () => {
      frame = 0;
      const readingLine = window.innerWidth <= 950 ? 165 : 116;
      const above = allIds
        .map((id) => {
          const target = document.getElementById(id);
          return target ? { id, top: target.getBoundingClientRect().top } : null;
        })
        .filter((entry): entry is { id: string; top: number } => entry !== null)
        .filter((entry) => entry.top <= readingLine)
        .sort((a, b) => b.top - a.top);
      setActiveSection(above[0]?.id ?? 'overview');
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(syncActive);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    onScroll();
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      window.removeEventListener('hashchange', selectHash);
    };
  }, []);

  const connected = Boolean(system && project && !error);
  const statusText = loading
    ? 'Connexion en cours'
    : connected
      ? 'Backend local connecté'
      : 'Backend indisponible';

  const ramPercent = system?.ram_total_gb
    ? Math.min(100, Math.max(0, (system.ram_available_gb / system.ram_total_gb) * 100))
    : 0;

  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">Passer au contenu principal</a>

      <aside className="sidebar" aria-label="Navigation Heretic Studio">
        <a className="brand" href="#overview" aria-label="Heretic Studio, retour à l’accueil">
          <span className="brand-mark" aria-hidden="true">H</span>
          <span className="brand-words">
            <strong>HERETIC</strong>
            <small>STUDIO <span>ALPHA</span></small>
          </span>
        </a>

        <nav aria-label="Navigation principale">
          {NAV_GROUPS.map((group) => (
            <div className="nav-group" key={group.label}>
              <p className="nav-title">{group.label}</p>
              <div className="nav-links">
                {group.items.map((item) => (
                  <a
                    className={'nav-item' + (activeSection === item.id ? ' active' : '')}
                    key={item.id}
                    href={'#' + item.id}
                    aria-current={activeSection === item.id ? 'location' : undefined}
                    onClick={() => setActiveSection(item.id)}
                  >
                    <StudioIcon name={item.icon} />
                    <span>{item.label}</span>
                  </a>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <span className="sidebar-local-icon" aria-hidden="true"><StudioIcon name="shield" /></span>
          <span><strong>Exécution locale</strong><small>Modèles sous ton contrôle</small></span>
        </div>
      </aside>

      <main id="main-content" tabIndex={-1}>
        <header className="topbar">
          <div className="topbar-location">
            <span className="topbar-overline">TON ESPACE DE TRAVAIL</span>
            <strong>Laboratoire IA</strong>
          </div>
          <div className={'connection-status' + (!connected && !loading ? ' unavailable' : '')} role="status" aria-live="polite">
            <span className="status-dot" aria-hidden="true" />
            <span>{statusText}</span>
          </div>
        </header>

        <div className="content">
          <section className="studio-hero" id="overview" aria-labelledby="hero-title">
            <div className="studio-hero-copy">
              <span className="eyebrow">HERETIC STUDIO · VERSION ALPHA</span>
              <h1 id="hero-title">Explore tes modèles.<br /><em>Expérimente en local.</em></h1>
              <p className="intro">
                Choisis un modèle, vérifie les ressources de ton ordinateur, puis lance une
                conversation locale. Chaque étape reste sous ton contrôle.
              </p>
              <div className="hero-actions">
                <a className="action-primary" href="#local-chat">
                  Ouvrir le chat local <StudioIcon name="arrow" />
                </a>
                <a className="action-secondary" href="#models">
                  Explorer les modèles <StudioIcon name="arrow" />
                </a>
              </div>
              <p className="hero-trust"><StudioIcon name="shield" />
                Aucun modèle n’est modifié par le chat. Les téléchargements demandent une confirmation.
              </p>
            </div>
            <div className="journey-card" aria-label="Parcours de découverte">
              <span className="journey-kicker">PARCOURS CONSEILLÉ</span>
              <h2>Trois étapes pour commencer</h2>
              <ol>
                <li><span className="journey-number">01</span><div><strong>Choisir</strong><small>Parcourir les modèles du catalogue</small></div><StudioIcon name="layers" /></li>
                <li><span className="journey-number">02</span><div><strong>Vérifier</strong><small>Estimer mémoire et compatibilité</small></div><StudioIcon name="gauge" /></li>
                <li><span className="journey-number">03</span><div><strong>Discuter</strong><small>Charger un modèle déjà téléchargé</small></div><StudioIcon name="message" /></li>
              </ol>
              <a className="journey-link" href="#models">Commencer le parcours <StudioIcon name="arrow" /></a>
            </div>
          </section>

          {error && (
            <div role="alert" className="error backend-alert">
              <StudioIcon name="info" />
              <div><strong>Connexion locale indisponible</strong><p>{error}</p></div>
              <button type="button" onClick={() => void refresh()} disabled={loading}>Réessayer</button>
            </div>
          )}

          <section className="machine-section" id="machine" aria-labelledby="machine-title">
            <div className="section-heading">
              <div>
                <span className="eyebrow">01 / ENVIRONNEMENT</span>
                <h2 id="machine-title">Ton ordinateur, en un coup d’œil</h2>
                <p className="section-subtitle">Données locales, sans téléchargement ni lancement de modèle.</p>
              </div>
              <button type="button" className="button-subtle" onClick={() => void refresh()} disabled={loading}>
                <StudioIcon name="refresh" /> {loading ? 'Analyse…' : 'Actualiser'}
              </button>
            </div>
            <div className="grid machine-grid" aria-busy={loading}>
              <article className="card metric-card">
                <div className="metric-top"><span>SYSTÈME</span><StudioIcon name="monitor" /></div>
                <div className="metric-value">{system?.os ?? '—'}</div>
                <p className="metric-detail">{system?.cpu ?? 'En attente des informations système'}</p>
              </article>
              <article className="card metric-card">
                <div className="metric-top"><span>MÉMOIRE RAM</span><StudioIcon name="memory" /></div>
                <div className="metric-value">{system ? system.ram_available_gb + ' Go' : '—'}</div>
                <p className="metric-detail">disponibles sur {system?.ram_total_gb ?? '—'} Go</p>
                <div className="memory-track" role="meter" aria-label="Part de RAM disponible"
                  aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(ramPercent)}>
                  <div style={{ width: ramPercent + '%' }} />
                </div>
              </article>
              <article className="card metric-card">
                <div className="metric-top"><span>CARTE GRAPHIQUE</span><StudioIcon name="cpu" /></div>
                <div className="metric-value">{system?.nvidia_gpus.length ?? '—'} <span className="metric-unit">GPU NVIDIA</span></div>
                <p className="metric-detail">{system?.nvidia_gpus.map((gpu) => gpu.name + ' · ' + gpu.memory_total_gb + ' Go VRAM').join(' ; ') || 'Non détecté avec cette sonde'}</p>
              </article>
              <article className="card metric-card">
                <div className="metric-top"><span>STOCKAGE LIBRE</span><StudioIcon name="storage" /></div>
                <div className="metric-value">{system?.disk_available_gb == null ? '—' : system.disk_available_gb + ' Go'}</div>
                <p className="metric-detail">sur le disque contenant le projet</p>
              </article>
            </div>
            {system && (
              <p className="system-disclaimer">
                <StudioIcon name="info" /> Ce diagnostic décrit ton matériel, sans certifier sa
                compatibilité avec un modèle. {system.gpu_detection_note}
              </p>
            )}
          </section>

          <Models />

          <section className="studio-outro" aria-label="Informations sur le projet">
            <article className="panel studio-about">
              <span className="eyebrow">LE MOTEUR</span>
              <h2>Heretic, côté technique</h2>
              <p>Les informations suivantes sont lues dans le projet Python installé.</p>
              <dl>
                <div><dt>Paquet</dt><dd>{project?.name ?? '—'}</dd></div>
                <div><dt>Version</dt><dd>{project?.version ?? '—'}</dd></div>
                <div><dt>Python requis</dt><dd>{project?.python ?? '—'}</dd></div>
              </dl>
            </article>
            <article className="panel studio-about" id="roadmap">
              <span className="eyebrow">PROCHAINEMENT</span>
              <h2>Expérimentations avancées</h2>
              <p>La modification et la comparaison de modèles seront proposées après validation technique et sécurité.</p>
              <div className="coming"><span>Chat local</span><b>Disponible</b></div>
              <div className="coming"><span>Comparaison des réponses</span><b>À venir</b></div>
              <div className="coming"><span>Optimisation Heretic</span><b>À venir</b></div>
            </article>
          </section>

          <footer>HERETIC STUDIO · EXPÉRIMENTAL · INFÉRENCE LOCALE SUR DEMANDE</footer>
        </div>
      </main>
    </div>
  );
}
