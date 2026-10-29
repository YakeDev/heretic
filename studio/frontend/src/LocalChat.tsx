import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { MarkdownMessage } from './MarkdownMessage';

type LocalModel = { model_id: string; revision: string };
type ReplyStats = {
  generated_tokens?: number;
  elapsed_seconds?: number;
  tokens_per_second?: number;
  finish_reason?: 'eos' | 'length' | 'unknown';
  max_new_tokens?: number;
  process_ram_gib?: number;
  torch_vram_gib?: number;
  torch_peak_vram_gib?: number;
};
type Message = { role: 'user' | 'assistant'; content: string; stats?: ReplyStats };
type ResponseStyle = 'neutral' | 'concise' | 'pedagogical';
type Resources = {
  ram_available_gb?: number;
  nvidia_gpus?: Array<{ name: string; memory_free_gb: number }>;
};
type Session = {
  session_id: string;
  model_id: string;
  revision: string;
  device: string;
  state: 'loading' | 'ready' | 'generating' | 'failed' | 'stopped';
  message?: string | null;
};
type Reply = {
  request_id: string;
  state: 'generating' | 'completed' | 'failed';
  answer?: string;
  message?: string;
  generated_tokens?: number;
  elapsed_seconds?: number;
  tokens_per_second?: number;
  finish_reason?: 'eos' | 'length' | 'unknown';
  max_new_tokens?: number;
  process_ram_gib?: number;
  torch_vram_gib?: number;
  torch_peak_vram_gib?: number;
};

const BASE = 'http://127.0.0.1:8765';

const CHAT_STATES: Record<Session['state'], string> = {
  loading: 'Chargement du modèle',
  ready: 'Modèle prêt à répondre',
  generating: 'Réponse en cours',
  failed: 'Chargement échoué',
  stopped: 'Modèle arrêté',
};

export function LocalChat() {
  const token = useRef('');
  const [models, setModels] = useState<LocalModel[]>([]);
  const [selected, setSelected] = useState('');
  const [device, setDevice] = useState<'cuda' | 'cpu'>('cuda');
  const [style, setStyle] = useState<ResponseStyle>('concise');
  const [maxNewTokens, setMaxNewTokens] = useState<128 | 256 | 384 | 512>(256);
  const [resources, setResources] = useState<Resources | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [requestId, setRequestId] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [pendingUserText, setPendingUserText] = useState('');
  const [notice, setNotice] = useState('Aucun modèle chargé.');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const call = useCallback(async <T,>(path: string, payload?: object): Promise<T> => {
    if (!token.current) {
      const sessionResponse = await fetch(BASE + '/api/downloads/session', {
        signal: AbortSignal.timeout(8000),
      });
      if (!sessionResponse.ok) throw new Error('Session locale indisponible.');
      const result = await sessionResponse.json() as { token: string };
      token.current = result.token;
    }
    const response = await fetch(BASE + path, {
      method: payload === undefined ? 'GET' : 'POST',
      headers: {
        'X-Heretic-Token': token.current,
        ...(payload === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      body: payload === undefined ? undefined : JSON.stringify(payload),
      signal: AbortSignal.timeout(12000),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({})) as { detail?: string };
      throw new Error(body.detail || 'Erreur HTTP ' + response.status);
    }
    return await response.json() as T;
  }, []);

  const refreshModels = useCallback(async () => {
    try {
      const data = await call<{ models: LocalModel[] }>('/api/chat/models');
      setModels(data.models);
      const existing = await call<{ session: Session | null }>('/api/chat/current');
      if (existing.session && existing.session.state !== 'stopped') {
        setSession(existing.session);
      }
      setSelected((value) => data.models.some((model) =>
        model.model_id + ':' + model.revision === value
      ) ? value : '');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Catalogue local inaccessible.');
    }
  }, [call]);

  useEffect(() => {
    void refreshModels();
  }, [refreshModels]);

  useEffect(() => {
    if (!session || !['loading', 'ready', 'generating'].includes(session.state)) return;
    const currentId = session.session_id;
    const timer = window.setInterval(() => {
      void call<Session>('/api/chat/' + currentId)
        .then((updated) => {
          setSession((old) => old?.session_id === currentId ? updated : old);
        })
        .catch(() => setNotice('Le processus local ne répond pas.'));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [call, session?.session_id, session?.state]);

  useEffect(() => {
    if (!session || !requestId) return;
    const currentSessionId = session.session_id;
    const currentRequestId = requestId;
    let alive = true;
    const timer = window.setInterval(() => {
      void call<Reply>(
        '/api/chat/' + currentSessionId + '/responses/' + currentRequestId,
      ).then((response) => {
        if (!alive || response.state === 'generating') return;
        if (response.state === 'completed') {
          setMessages((old) => [...old, {
            role: 'user', content: pendingUserText,
          }, {
            role: 'assistant', content: response.answer ?? '',
            stats: {
              generated_tokens: response.generated_tokens,
              elapsed_seconds: response.elapsed_seconds,
              tokens_per_second: response.tokens_per_second,
              finish_reason: response.finish_reason,
              max_new_tokens: response.max_new_tokens,
              process_ram_gib: response.process_ram_gib,
              torch_vram_gib: response.torch_vram_gib,
              torch_peak_vram_gib: response.torch_peak_vram_gib,
            },
          }]);
          setPendingUserText('');
          setNotice(response.finish_reason === 'length'
            ? 'Limite de génération atteinte : la réponse peut être incomplète.'
            : 'Réponse terminée : ' + (response.generated_tokens ?? 0) + ' nouveaux tokens.');
          void call<Resources>('/api/system').then(setResources).catch(() => {});
        } else {
          setError(response.message ?? 'Le modèle n’a pas pu répondre.');
          // Restore the failed prompt without asking the user to retype it.
          setDraft((current) => current || pendingUserText);
          setPendingUserText('');
          setNotice('Échec de génération : tu peux réessayer sans recharger le modèle.');
        }
        setRequestId('');
      }).catch((cause) => {
        if (alive) setError(cause instanceof Error ? cause.message : 'Erreur de réponse.');
      });
    }, 1500);
    return () => { alive = false; window.clearInterval(timer); };
  }, [call, session?.session_id, requestId, pendingUserText]);

  async function start() {
    const model = models.find((m) => m.model_id + ':' + m.revision === selected);
    if (!model) return;
    setBusy(true);
    setError('');
    setMessages([]);
    setNotice('Chargement du modèle local...');
    try {
      const started = await call<Session>('/api/chat/start', {
        model_id: model.model_id,
        revision: model.revision,
        device,
      });
      setSession(started);
      void call<Resources>('/api/system').then(setResources).catch(() => {});
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Échec du démarrage.');
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      await call('/api/chat/' + session.session_id + '/stop', {});
      setSession(null);
      setRequestId('');
      setPendingUserText('');
      setNotice('Session arrêtée : mémoire libérée par le processus.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Impossible d’arrêter la session.');
    } finally {
      setBusy(false);
    }
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!session || session.state !== 'ready' || !text || requestId) return;
    // Limit context deliberately; session can be reset without losing control.
    const history = messages.slice(-8);
    const outgoing: Message[] = [...history, { role: 'user', content: text }];
    if (outgoing.reduce((total, msg) => total + msg.content.length, 0) > 6000) {
      setError('Historique trop long. Arrête et redémarre le chat pour continuer.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const response = await call<{ request_id: string }>(
        '/api/chat/' + session.session_id + '/generate',
        {
          messages: outgoing.map(({ role, content }) => ({ role, content })),
          max_new_tokens: maxNewTokens,
          style,
        },
      );
      setDraft('');
      setPendingUserText(text);
      setRequestId(response.request_id);
      setNotice('Génération en cours…');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Impossible d’envoyer la question.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="local-chat-panel" id="local-chat" aria-labelledby="local-chat-title">
      <div className="eyebrow">06 / PREMIER CHAT LOCAL</div>
      <h2 id="local-chat-title">Discuter avec ton modèle local</h2>
      <p>
        Sélectionne un modèle déjà téléchargé et démarre une conversation.
        Les réponses sont générées sur ton ordinateur, sans API de génération distante.
      </p>
      <div className="chat-settings">
        <label>Modèle disponible
          <select
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
            disabled={session !== null}
          >
            <option value="">Sélectionner un modèle téléchargé</option>
            {models.map((item) => (
              <option key={item.model_id + item.revision} value={item.model_id + ':' + item.revision}>
                {item.model_id} · {item.revision.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        <label>Périphérique
          <select
            value={device}
            onChange={(event) => setDevice(event.target.value as 'cuda' | 'cpu')}
            disabled={session !== null}
          >
            <option value="cuda">GPU NVIDIA (CUDA)</option>
            <option value="cpu">CPU (expérimental, très lent)</option>
          </select>
        </label>
      </div>
      <details className="chat-options">
        <summary>Personnaliser les réponses <span>Style et longueur · facultatif</span></summary>
        <div className="chat-tuning" aria-label="Paramètres des réponses">
        <label>Style de réponse
          <select
            value={style}
            onChange={(event) => setStyle(event.target.value as ResponseStyle)}
            disabled={Boolean(requestId) || busy}
          >
            <option value="concise">Concis — priorité aux consignes</option>
            <option value="neutral">Standard — réponse directe</option>
            <option value="pedagogical">Pédagogique — exemples</option>
          </select>
        </label>
        <label>Longueur maximale
          <select
            value={maxNewTokens}
            onChange={(event) => setMaxNewTokens(Number(event.target.value) as 128 | 256 | 384 | 512)}
            disabled={Boolean(requestId) || busy}
          >
            <option value={128}>128 tokens · court</option>
            <option value={256}>256 tokens · équilibré</option>
            <option value={384}>384 tokens · long</option>
            <option value={512}>512 tokens · très long (plus lent)</option>
          </select>
        </label>
      </div>
        <p className="chat-hint">
          Ces paramètres orientent le modèle mais ne garantissent pas son exactitude.
        </p>
      </details>
      <div className="chat-actions">
        <button type="button" onClick={() => void refreshModels()} disabled={busy}>
          ↻ Actualiser les modèles téléchargés
        </button>
        {session === null ? (
          <button type="button" onClick={() => void start()} disabled={!selected || busy}>
            Charger le modèle
          </button>
        ) : (
          <button type="button" onClick={() => void stop()} disabled={busy}>
            Arrêter le modèle
          </button>
        )}
      </div>
      {models.length === 0 && (
        <p className="chat-hint">Aucun modèle local disponible. <a href="#downloads">Préparer un téléchargement</a>, puis actualiser cette liste.</p>
      )}
      <div className={'chat-state ' + (session ? 'is-' + session.state : 'is-idle')} role="status" aria-live="polite">
        <span className="status-dot" aria-hidden="true" />
        {session ? CHAT_STATES[session.state] : notice}
        {session?.message ? ' · ' + session.message : ''}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="chat-transcript" aria-label="Conversation locale">
        {messages.length === 0 && <p className="chat-empty">Les réponses du modèle apparaîtront ici après son chargement.</p>}
        {messages.map((message, index) => (
          <div className={'chat-bubble ' + message.role} key={index}>
            <strong>{message.role === 'user' ? 'Vous' : 'Modèle IA'}</strong>
            {message.role === 'assistant'
              ? <MarkdownMessage content={message.content} />
              : <p>{message.content}</p>}
            {message.stats && (
              <div className="chat-message-metrics">
                <span>{message.stats.generated_tokens ?? '—'} tokens</span>
                <span>{message.stats.elapsed_seconds ?? '—'} s de génération</span>
                <span>{message.stats.tokens_per_second ?? '—'} tokens/s</span>
                {typeof message.stats.process_ram_gib === 'number' && (
                  <span>Processus : {message.stats.process_ram_gib.toFixed(2)} Gio RAM</span>
                )}
                {typeof message.stats.torch_vram_gib === 'number' && (
                  <span>PyTorch CUDA : {message.stats.torch_vram_gib.toFixed(2)} Gio VRAM allouée</span>
                )}
                {typeof message.stats.torch_peak_vram_gib === 'number' && (
                  <span>Pic CUDA : {message.stats.torch_peak_vram_gib.toFixed(2)} Gio</span>
                )}
                {message.stats.finish_reason === 'length' && (
                  <strong className="chat-truncation">
                    Limite atteinte : cette réponse peut être tronquée.
                  </strong>
                )}
              </div>
            )}
          </div>
        ))}
        {pendingUserText && (
          <div className="chat-bubble user">
            <strong>Vous</strong><p>{pendingUserText}</p>
          </div>
        )}
        {requestId && <p className="chat-hint">Le modèle prépare sa réponse…</p>}
      </div>
      {messages.some((message) => message.stats) && (
        <details className="chat-performance-details">
          <summary>Voir les performances de la session</summary>
          <div className="chat-performance" aria-label="Performances de la session">
            <strong>Performances observées</strong>
          <span>
            {messages.filter((message) => message.role === 'assistant').length} réponses ·{' '}
            {(() => {
              const rates = messages
                .filter((message) => message.role === 'assistant')
                .map((message) => message.stats?.tokens_per_second)
                .filter((value): value is number => typeof value === 'number' && value > 0);
              return rates.length
                ? (rates.reduce((sum, value) => sum + value, 0) / rates.length).toFixed(1) + ' tokens/s en moyenne'
                : 'vitesse non mesurée';
            })()}
          </span>
          {typeof resources?.ram_available_gb === 'number' && (
            <span>RAM libre (instantané système) : {resources.ram_available_gb.toFixed(1)} Go</span>
          )}
          {resources?.nvidia_gpus?.[0] && (
            <span>VRAM libre (instantané GPU) : {resources.nvidia_gpus[0].memory_free_gb.toFixed(1)} Go</span>
          )}
          <small>Durée et vitesse mesurent la génération seule. Mémoire du processus et allocations PyTorch CUDA indiquées par réponse ; les instantanés RAM/VRAM libres sont des mesures système, pas une attribution précise au seul modèle.</small>
          </div>
        </details>
      )}
      <details className="chat-evaluation-details">
        <summary>Tester la qualité des réponses</summary>
        <div className="chat-evaluation">
          <strong>Questions de test</strong>
        <button
          type="button"
          disabled={Boolean(requestId) || busy}
          onClick={() => setDraft('Explique la différence entre TCP et UDP en trois phrases maximum.')}
        >
          Précision et consignes
        </button>
        <button
          type="button"
          disabled={Boolean(requestId) || busy}
          onClick={() => setDraft('Lequel des deux est généralement privilégié pour un appel vidéo en temps réel ? Pourquoi ?')}
        >
          Continuité du contexte
        </button>
        <p className="chat-hint">Ces questions servent à comparer les réponses, sans attribuer de note automatique de justesse.</p>
        </div>
      </details>
      <form className="chat-compose" onSubmit={(event) => void send(event)}>
        <label htmlFor="chat-message">Ton message <span className="chat-compose-hint">{draft.length}/2000 caractères</span></label>
        <textarea
          id="chat-message"
          rows={3}
          maxLength={2000}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Exemple : Explique-moi la différence entre TCP et UDP."
          disabled={session?.state !== 'ready' || Boolean(requestId) || busy}
        />
        <button
          type="submit"
          disabled={session?.state !== 'ready' || Boolean(requestId) || busy || !draft.trim()}
        >
          Envoyer le message
        </button>
      </form>
      <p className="chat-hint">
        Attention : pas de garantie sur l’exactitude des réponses. Le mode chat ne modifie pas le modèle
        et n’active pas les expériences Heretic. Pour interrompre un chargement ou une génération,
        utilise « Arrêter le modèle ».
      </p>
    </section>
  );
}
