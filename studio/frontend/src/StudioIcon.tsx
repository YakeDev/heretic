export type IconName =
  | 'home' | 'cpu' | 'layers' | 'gauge' | 'settings' | 'download'
  | 'message' | 'flask' | 'monitor' | 'memory' | 'storage'
  | 'shield' | 'arrow' | 'refresh' | 'info';

export function StudioIcon({ name }: { name: IconName }) {
  let graphic: React.ReactNode;
  switch (name) {
    case 'home':
      graphic = <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" /><path d="M9 21v-8h6v8" /></>; break;
    case 'cpu':
      graphic = <><rect x="5" y="5" width="14" height="14" rx="2" /><rect x="9" y="9" width="6" height="6" /><path d="M9 2v3m6-3v3M9 19v3m6-3v3M2 9h3m-3 6h3m14-6h3m-3 6h3" /></>; break;
    case 'layers':
      graphic = <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></>; break;
    case 'gauge':
      graphic = <><path d="M3 17a9 9 0 1 1 18 0" /><path d="m12 17 4-5" /><path d="M8 20h8" /></>; break;
    case 'settings':
      graphic = <><circle cx="12" cy="12" r="3" /><path d="m9.4 2 .6 2.3a8 8 0 0 0-2 1L5.8 4.4 3.4 8.6l1.8 1.6a8 8 0 0 0 0 3.6l-1.8 1.6 2.4 4.2 2.2-.9a8 8 0 0 0 2 1l.6 2.3h4.8l.6-2.3a8 8 0 0 0 2-1l2.2.9 2.4-4.2-1.8-1.6a8 8 0 0 0 0-3.6l1.8-1.6-2.4-4.2-2.2.9a8 8 0 0 0-2-1L14.6 2Z" transform="translate(0 -0.5) scale(1 0.98)" /></>; break;
    case 'download':
      graphic = <><path d="M12 3v12m-4-4 4 4 4-4" /><path d="M4 17v3h16v-3" /></>; break;
    case 'message':
      graphic = <path d="M20 15a4 4 0 0 1-4 4H8l-4 3V7a4 4 0 0 1 4-4h8a4 4 0 0 1 4 4v8Z" />; break;
    case 'flask':
      graphic = <><path d="M9 3h6m-5 0v7l-5.5 9a2 2 0 0 0 1.7 3h11.6a2 2 0 0 0 1.7-3L14 10V3M8 16h8" /></>; break;
    case 'monitor':
      graphic = <><rect x="3" y="4" width="18" height="14" rx="2" /><path d="M8 22h8m-4-4v4" /></>; break;
    case 'memory':
      graphic = <><rect x="3" y="7" width="18" height="10" rx="2" /><path d="M7 10v4m4-4v4m4-4v4M6 4v3m6-3v3m6-3v3M6 17v3m6-3v3m6-3v3" /></>; break;
    case 'storage':
      graphic = <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M3 11h18m-13 5h.01m5 0h.01" /></>; break;
    case 'shield':
      graphic = <><path d="M12 2 20 5v6c0 5-3.1 8.5-8 11-4.9-2.5-8-6-8-11V5l8-3Z" /><path d="m9 12 2 2 4-4" /></>; break;
    case 'arrow':
      graphic = <><path d="M4 12h15m-6-6 6 6-6 6" /></>; break;
    case 'refresh':
      graphic = <><path d="M20 11a8 8 0 0 0-14-5L4 8m0-5v5h5" /><path d="M4 13a8 8 0 0 0 14 5l2-2m0 5v-5h-5" /></>; break;
    case 'info':
      graphic = <><circle cx="12" cy="12" r="9" /><path d="M12 11v5m0-9h.01" /></>; break;
  }
  return <svg className="studio-icon" width="19" height="19" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"
    strokeLinejoin="round" aria-hidden="true" focusable="false">{graphic}</svg>;
}
