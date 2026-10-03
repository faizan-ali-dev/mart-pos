import { useEffect } from 'react';

export function Modal({ title, onClose, children, wide }) {
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose && onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal${wide ? ' wide' : ''}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="btn icon" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function Spinner({ label }) {
  return (
    <div className="spinner-wrap">
      <div className="spinner" />
      {label && <span>{label}</span>}
    </div>
  );
}

export function EmptyState({ title, hint }) {
  return (
    <div className="empty">
      <div className="empty-title">{title || 'Kuch nahi mila'}</div>
      {hint && <div className="empty-hint">{hint}</div>}
    </div>
  );
}

export function Field({ label, children, span }) {
  return (
    <label className={`field${span ? ' span' : ''}`}>
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

const TONES = { green: 'b-green', red: 'b-red', amber: 'b-amber', blue: 'b-blue', gray: 'b-gray', purple: 'b-purple' };
export function Badge({ tone = 'gray', children }) {
  return <span className={`badge ${TONES[tone] || TONES.gray}`}>{children}</span>;
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="error-box">
      <span>⚠ {String(error)}</span>
      {onRetry && <button className="btn small" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function PageHead({ title, urdu, actions }) {
  return (
    <div className="page-head">
      <div>
        <h2>{title} {urdu && <span className="urdu-sub">{urdu}</span>}</h2>
      </div>
      <div className="page-actions">{actions}</div>
    </div>
  );
}
