import { useCallback, useEffect, useRef, useState } from "react";

// One data-fetching hook for the whole product, so every page reports
// loading / error / empty identically. Never substitutes a fallback value
// on failure — a failed call surfaces as an error the page renders, never
// as invented data.
export function useApi(fetcher, deps = [], { skip = false } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(!skip);
  const [nonce, setNonce] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (skip) { setLoading(false); return; }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.resolve()
      .then(() => fetcherRef.current())
      .then((body) => { if (!cancelled) setData(body); })
      .catch((err) => { if (!cancelled) setError(err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, skip, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload, setData };
}

// Some endpoints answer 409 when a precondition isn't met yet (no rule pack
// adopted, nothing evaluated). That's an expected state to render honestly,
// not a page-breaking error — this variant keeps it separate.
export function useOptionalApi(fetcher, deps = [], { skip = false } = {}) {
  const { data, error, loading, reload } = useApi(fetcher, deps, { skip });
  return { data, unavailableReason: error ? String(error.message || error) : null, loading, reload };
}
