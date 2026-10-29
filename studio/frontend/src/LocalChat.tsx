import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';

type LocalModel = { model_id: string; revision: string };
type Message = { role: 'user' | 'assistant'; content: string };
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
};

const BASE = 'http://127.0.0.1:8765';

export function LocalChat() {
  const token = useRef('');
  const [models, setModels] = useState<LocalModel[]>([]);
  const [selected, setSelected] = useState('');
  const [device, setDevice] = useState<'cuda' | 'cpu'>('cuda');
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
          }, { role: 'assistant', content: response.answer ?? '' }]);
          setPendingUserText('');
          setNotice('Réponse terminée · ' + (response.generated_tokens ?? 0) + ' nouveaux tokens.');
        } else {
          setError(response.message ?? 'Le modèle n’a pas pu répondre.');
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
        { messages: outgoing, max_new_tokens: 128 },
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
      <h2 id="local-chat-title">Parler avec un modèle téléchargé</h2>
      <p>
        Mode expérimental : un modèle est chargé dans un processus local isolé.
        Aucun appel à une API de génération en ligne. Le premier chargement peut être lent.
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
        <p className="chat-hint">Aucun modèle local validé. Télécharge d’abord les poids depuis la section précédente.</p>
      )}
      <div className="chat-state" role="status">
        <span className="status-dot" />
        {session ? 'État du modèle : ' + session.state : notice}
        {session?.message ? ' · ' + session.message : ''}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="chat-transcript" aria-label="Conversation locale">
        {messages.length === 0 && <p className="chat-empty">Les réponses du modèle apparaîtront ici après son chargement.</p>}
        {messages.map((message, index) => (
          <div className={'chat-bubble ' + message.role} key={index}>
            <strong>{message.role === 'user' ? 'Vous' : 'Modèle IA'}</strong>
            <p>{message.content}</p>
          </div>
        ))}
        {pendingUserText && (
          <div className="chat-bubble user">
            <strong>Vous</strong><p>{pendingUserText}</p>
          </div>
        )}
        {requestId && <p className="chat-hint">Le modèle prépare sa réponse…</p>}
      </div>
      <form className="chat-compose" onSubmit={(event) => void send(event)}>
        <label htmlFor="chat-message">Ton message</label>
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
          Envoyer au modèle local
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
