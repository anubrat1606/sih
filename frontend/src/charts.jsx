import "./charts.css";

// Chart primitives -- round 4, R2. Pure SVG, no chart library, matching this
// project's existing choice to hand-draw the Evidence Graph rather than pull
// in a graph library. Every colour comes from tokens.css; every shape has an
// explicit fill (or explicit fill="none" with a stroke) so nothing falls
// back to SVG's implicit black fill, which reads as a bug in dark mode.

const RISK_LEVELS = ["low", "medium", "high"];

// Horizontal stacked bar -- segment widths genuinely proportional to the
// three counts, drawn to real scale (a 0-count segment renders 0 width, not
// an evenly-thirded bar). Same .risk-bar* classes and risk palette
// DashboardPage.jsx's own inline version already uses (see that file's
// comment: this replaces it once merged) -- never a new colour for this.
// Renders its own total-count caption beneath the bar.
export function RiskDistributionBar({ low, medium, high }) {
  const counts = { low, medium, high };
  const total = low + medium + high;

  if (total === 0) {
    return <p className="hint">No data to show.</p>;
  }

  return (
    <div className="rdb">
      <div
        className="risk-bar"
        role="img"
        aria-label={`Risk distribution: ${low} low, ${medium} medium, ${high} high`}
      >
        {RISK_LEVELS.map((level) => {
          const count = counts[level];
          if (count === 0) return null;
          const pct = (count / total) * 100;
          return (
            <div
              key={level}
              className={`risk-bar-segment risk-bar-${level}`}
              style={{ width: `${pct}%` }}
              title={`${level.toUpperCase()}: ${count}`}
            >
              {pct >= 10 && <span className="rdb-segment-label">{count}</span>}
            </div>
          );
        })}
      </div>
      <p className="hint rdb-caption">
        {RISK_LEVELS.map((level) => `${level.toUpperCase()} ${counts[level]}`).join(" · ")}
        {" — "}{total} total
      </p>
    </div>
  );
}

// Small inline line/area chart. `values` may be empty (a flat baseline, not
// an error) or hold a single value (a single point, never a divide-by-zero
// on the x-axis step calculation).
export function Sparkline({ values, width = 120, height = 32 }) {
  const pad = 3;

  if (!values || values.length === 0) {
    return (
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height}
           className="sparkline" role="img" aria-label="No data">
        <line x1={pad} y1={height / 2} x2={width - pad} y2={height / 2}
              stroke="var(--color-border-strong)" strokeWidth="1.5" />
      </svg>
    );
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1; // all-equal values: avoid a divide-by-zero flatline crash
  const usableW = width - pad * 2;
  const usableH = height - pad * 2;
  const stepX = values.length > 1 ? usableW / (values.length - 1) : 0;
  const points = values.map((v, i) => [
    pad + i * stepX,
    pad + usableH - ((v - min) / range) * usableH,
  ]);

  if (points.length === 1) {
    const [x, y] = points[0];
    return (
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height}
           className="sparkline" role="img" aria-label={`Single value ${values[0]}`}>
        <circle cx={x} cy={y} r="2.5" fill="var(--color-accent)" />
      </svg>
    );
  }

  const linePath = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x},${y}`).join(" ");
  const areaPath =
    `${linePath} L${points[points.length - 1][0]},${height - pad} L${points[0][0]},${height - pad} Z`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} className="sparkline"
         role="img" aria-label={`Trend from ${values[0]} to ${values[values.length - 1]}`}>
      <path d={areaPath} fill="var(--color-accent-bg)" stroke="none" />
      <path d={linePath} fill="none" stroke="var(--color-accent)" strokeWidth="1.5" />
    </svg>
  );
}

// A single big-number tile -- matches .metric-value's existing null-handling
// convention (Metric in components.jsx): an em dash, never a fabricated 0,
// when nothing could be determined.
export function StatTile({ label, value }) {
  return (
    <div className="stat-tile">
      <div className="stat-tile-value mono">{value === null || value === undefined ? "—" : value}</div>
      <div className="stat-tile-label">{label}</div>
    </div>
  );
}
