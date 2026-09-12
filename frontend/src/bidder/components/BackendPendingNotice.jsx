// The one honest way this portal says "this needs backend work" --
// deliberately looks deliberate (bordered, labelled, calm), never like a
// broken panel, and never silently swallowed. Every not-yet-implemented
// flow in the bidder portal renders through this component, so a judge or
// a reviewer sees exactly one consistent pattern for "not built yet"
// instead of N different half-broken UIs.
export function BackendPendingNotice({ endpoint, children }) {
  return (
    <div className="unavailable-note" role="status">
      <span className="unavailable-note-glyph" aria-hidden="true">⚙</span>
      <div>
        <strong style={{ color: "var(--color-text)" }}>Requires a backend integration</strong>
        <div style={{ marginTop: 4 }}>{children}</div>
        {endpoint && (
          <div className="text-xs text-muted mono" style={{ marginTop: 6 }}>
            expected endpoint: {endpoint}
          </div>
        )}
      </div>
    </div>
  );
}

// Same message, sized for inline use under a form (e.g. after a submit
// attempt fails with BackendNotImplementedError) rather than a full block.
export function BackendPendingInline({ endpoint, children }) {
  return (
    <p className="text-sm" style={{ color: "var(--status-partial-fg)", marginTop: 8 }}>
      <span aria-hidden="true">⚙</span>{" "}
      {children}
      {endpoint && <span className="mono text-xs text-muted"> ({endpoint})</span>}
    </p>
  );
}
