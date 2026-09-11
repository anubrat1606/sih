import "./skeleton.css";

// A shimmering bar standing in for one line of text. Height matches
// --text-base's line box so it drops into a layout exactly where the real
// text will be -- no layout shift when the real content replaces it.
export function SkeletonLine({ width = "100%" }) {
  return <div className="skeleton skeleton-line" style={{ width }} aria-hidden="true" />;
}

// Matches .card's real padding/border/radius (App.css) exactly, so a real
// <div className="card"> and this placeholder occupy the same footprint.
export function SkeletonCard() {
  return (
    <div className="card skeleton-card" aria-hidden="true">
      <SkeletonLine width="55%" />
      <SkeletonLine width="90%" />
      <SkeletonLine width="40%" />
    </div>
  );
}

// Matches .evidence-table's real row height and border treatment by reusing
// that class directly, rather than approximating it with a second table
// style that could quietly drift out of sync.
export function SkeletonTable({ rows = 4, columns = 4 }) {
  return (
    <table className="evidence-table skeleton-table" aria-hidden="true">
      <tbody>
        {Array.from({ length: rows }).map((_, r) => (
          <tr key={r}>
            {Array.from({ length: columns }).map((_, c) => (
              <td key={c}>
                <SkeletonLine width={c === 0 ? "70%" : "100%"} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
