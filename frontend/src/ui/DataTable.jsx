import { useMemo, useState } from "react";
import { EmptyState, LoadingTable } from "./primitives";

// One table component for the whole product, so every list — tenders,
// bidders, documents, verifications, audit events — sorts, searches and
// filters identically. Columns declare how to render and how to sort; the
// table never reaches into a row's shape itself.
//
// column = {
//   key, header, render(row), sortValue(row)?, searchValue(row)?,
//   width?, align?, className?
// }
export function DataTable({
  columns,
  rows,
  loading,
  error,
  getRowKey,
  searchPlaceholder = "Search…",
  filters = [],              // [{ id, label, options: [{value,label}], value, onChange }]
  emptyTitle = "Nothing here yet",
  emptyMessage,
  emptyAction,
  initialSort,               // { key, direction: "asc"|"desc" }
  onRowClick,
  toolbarExtra,
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState(initialSort || null);

  const searched = useMemo(() => {
    if (!rows) return null;
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) =>
      columns.some((c) => {
        const v = c.searchValue ? c.searchValue(row) : c.sortValue ? c.sortValue(row) : null;
        return v !== null && v !== undefined && String(v).toLowerCase().includes(q);
      })
    );
  }, [rows, query, columns]);

  const sorted = useMemo(() => {
    if (!searched || !sort) return searched;
    const col = columns.find((c) => c.key === sort.key);
    if (!col || !col.sortValue) return searched;
    const dir = sort.direction === "desc" ? -1 : 1;
    return [...searched].sort((a, b) => {
      const av = col.sortValue(a), bv = col.sortValue(b);
      if (av === bv) return 0;
      if (av === null || av === undefined) return 1;   // unknowns sink, never sort as zero
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [searched, sort, columns]);

  function toggleSort(key) {
    setSort((cur) => {
      if (!cur || cur.key !== key) return { key, direction: "asc" };
      if (cur.direction === "asc") return { key, direction: "desc" };
      return null;
    });
  }

  const hasToolbar = Boolean(rows && (rows.length > 0 || query)) || filters.length > 0 || toolbarExtra;

  if (loading) return <LoadingTable columns={columns.length} />;

  return (
    <div>
      {hasToolbar && (
        <div className="toolbar">
          <div className="toolbar-search">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={searchPlaceholder}
              aria-label={searchPlaceholder}
            />
          </div>
          {filters.map((f) => (
            <div key={f.id} className="row" style={{ gap: 6 }}>
              <label className="field-hint" htmlFor={`filter-${f.id}`}>{f.label}</label>
              <select id={`filter-${f.id}`} value={f.value} onChange={(e) => f.onChange(e.target.value)}
                      style={{ width: "auto", minWidth: 130 }}>
                {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          ))}
          {toolbarExtra}
          {sorted && <span className="toolbar-count mono">{sorted.length} of {rows.length}</span>}
        </div>
      )}

      {error ? (
        <div className="table-frame"><div style={{ padding: 20 }}>
          <p className="error-note" role="alert"><span aria-hidden="true">⚠</span> {String(error.message || error)}</p>
        </div></div>
      ) : !sorted || sorted.length === 0 ? (
        <div className="table-frame">
          <EmptyState
            glyph={query ? "⌕" : "◌"}
            title={query ? "No matches" : emptyTitle}
            message={query ? `Nothing matches “${query}”.` : emptyMessage}
            action={query ? null : emptyAction}
          />
        </div>
      ) : (
        <div className="table-frame">
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  {columns.map((c) => (
                    <th
                      key={c.key}
                      style={c.width ? { width: c.width } : undefined}
                      className={[c.sortValue ? "sortable" : "", c.align === "right" ? "cell-actions" : ""].filter(Boolean).join(" ")}
                      onClick={c.sortValue ? () => toggleSort(c.key) : undefined}
                      aria-sort={sort?.key === c.key ? (sort.direction === "asc" ? "ascending" : "descending") : undefined}
                    >
                      {c.header}
                      {c.sortValue && (
                        <span className="sort-caret" aria-hidden="true">
                          {sort?.key === c.key ? (sort.direction === "asc" ? "▲" : "▼") : "↕"}
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map((row) => (
                  <tr
                    key={getRowKey(row)}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    style={onRowClick ? { cursor: "pointer" } : undefined}
                  >
                    {columns.map((c) => (
                      <td key={c.key} className={[c.className, c.align === "right" ? "cell-actions" : ""].filter(Boolean).join(" ")}>
                        {c.render(row)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
