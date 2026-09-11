import { useEffect, useRef, useState } from "react";
import "./searchFilterBar.css";

// Generic list-filtering control -- round 4, R1. Not hardcoded to tenders or
// bidders, so it can be reused anywhere a list needs search + sort. Renders
// ONLY its own search input + sort <select>; the caller (Anubrat, Phase 7)
// owns rendering the filtered/sorted result.
//
// items: array of plain objects, owned entirely by the caller.
// searchKeys: array of property names to case-insensitive substring-match
//   against. Matches if ANY key matches.
// sortOptions: array of { label, compare(a, b) }, rendered as a <select>;
//   the first option is the default/initial sort. Omit or pass an empty
//   array to hide the sort control entirely.
// onChange(filteredAndSortedItems): called on mount and on every change to
//   the query or sort selection -- deliberately NOT re-triggered merely
//   because the caller re-rendered and passed a new `items`/`sortOptions`
//   array by reference (a caller that recreates those inline every render,
//   while storing the result in state, would otherwise loop forever: its own
//   re-render recreates the array, which would re-fire the effect, which
//   updates state, which re-renders the caller -- indefinitely). The latest
//   items/searchKeys/sortOptions/onChange are always read fresh at query- or
//   sort-change time via a ref, so this never acts on stale data either.
// placeholder: optional input placeholder text, defaults to "Search…".
export function SearchFilterBar({ items, searchKeys, sortOptions, onChange, placeholder }) {
  const [query, setQuery] = useState("");
  const [sortIndex, setSortIndex] = useState(0);

  const latest = useRef({ items, searchKeys, sortOptions, onChange });
  // Refs are for effects/handlers, never assigned during render -- kept in
  // sync here instead, an effect with no dependency array so it runs after
  // every render (declared before the notify effect below so, on any commit
  // where both fire, this one updates the ref first).
  useEffect(() => {
    latest.current = { items, searchKeys, sortOptions, onChange };
  });

  useEffect(() => {
    const { items, searchKeys, sortOptions, onChange } = latest.current;
    const q = query.trim().toLowerCase();
    const filtered = q
      ? items.filter((item) =>
          searchKeys.some((key) => String(item[key] ?? "").toLowerCase().includes(q)))
      : items.slice();
    const option = sortOptions && sortOptions[sortIndex];
    if (option) filtered.sort(option.compare);
    onChange(filtered);
  }, [query, sortIndex]);

  return (
    <div className="sfb-bar">
      <input
        type="text"
        className="sfb-search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder || "Search…"}
        aria-label={placeholder || "Search"}
      />
      {sortOptions && sortOptions.length > 0 && (
        <select
          className="sfb-sort"
          value={sortIndex}
          onChange={(e) => setSortIndex(Number(e.target.value))}
          aria-label="Sort by"
        >
          {sortOptions.map((option, i) => (
            <option key={option.label} value={i}>{option.label}</option>
          ))}
        </select>
      )}
    </div>
  );
}
