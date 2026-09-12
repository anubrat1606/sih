import { useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { BACKEND_URL, authHeaders } from "../api";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

// The demo axiom made concrete: click a verdict, land on the exact
// highlighted line of the actual source PDF. `region` is [x0, top, x1,
// bottom] in PDF points, already top-down (pdfplumber's convention, the
// same one the extraction pipeline records with) — which is how a canvas is
// addressed too, so no Y-flip is needed, only the render scale.
function PdfCanvas({ documentSha256, page, region, scale, onNumPages }) {
  const canvasRef = useRef(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pageSize, setPageSize] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const doc = await pdfjsLib.getDocument({
          url: `${BACKEND_URL}/documents/${documentSha256}`,
          httpHeaders: authHeaders(),
        }).promise;
        if (cancelled) return;
        onNumPages?.(doc.numPages);
        const pdfPage = await doc.getPage(page);
        const viewport = pdfPage.getViewport({ scale });
        const canvas = canvasRef.current;
        if (!canvas) return;
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        await pdfPage.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
        if (cancelled) return;
        setPageSize({ width: viewport.width, height: viewport.height });
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onNumPages is a setter; stable identity not required
  }, [documentSha256, page, scale]);

  const box = region && pageSize && (() => {
    const [x0, top, x1, bottom] = region;
    return {
      position: "absolute",
      left: x0 * scale, top: top * scale,
      width: (x1 - x0) * scale, height: (bottom - top) * scale,
      border: "2px solid var(--highlight-overlay-border)",
      background: "var(--highlight-overlay-bg)",
      borderRadius: 2,
      pointerEvents: "none",
    };
  })();

  return (
    <div className="pdf-canvas-wrap">
      {loading && <p className="text-secondary text-sm" style={{ padding: 16 }}>Rendering page {page}…</p>}
      {error && (
        <p className="error-note" style={{ margin: 16 }} role="alert">
          <span aria-hidden="true">⚠</span>
          Could not load the source document: {String(error.message || error)}
        </p>
      )}
      <canvas ref={canvasRef} style={{ display: loading || error ? "none" : "block" }} />
      {box && <div style={box} aria-hidden="true" />}
    </div>
  );
}

export default function PdfEvidenceViewer({ documentSha256, page, region }) {
  const [expanded, setExpanded] = useState(false);
  const [currentPage, setCurrentPage] = useState(page);
  const [numPages, setNumPages] = useState(null);
  const closeRef = useRef(null);

  // A different verdict's trail can reuse this viewer for a different
  // document/page — reset to the newly highlighted page rather than leaving
  // it pointed where the previous one left off. Adjusted during render
  // (React's own recommended pattern), not in an effect.
  const [trackedKey, setTrackedKey] = useState(`${documentSha256}:${page}`);
  const key = `${documentSha256}:${page}`;
  if (key !== trackedKey) {
    setTrackedKey(key);
    setCurrentPage(page);
  }

  useEffect(() => {
    if (!expanded) return;
    closeRef.current?.focus();
    function onKey(e) { if (e.key === "Escape") setExpanded(false); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [expanded]);

  return (
    <>
      <div className="card" style={{ overflow: "hidden" }}>
        <div className="pdf-toolbar">
          <span className="text-xs text-muted mono">page {page} · highlighted region</span>
          <span className="spacer" />
          <button type="button" className="btn btn-sm btn-secondary" onClick={() => setExpanded(true)}>
            View source document ⤢
          </button>
        </div>
        <div className="pdf-frame">
          <PdfCanvas documentSha256={documentSha256} page={page} region={region} scale={1.4} />
        </div>
      </div>

      {expanded && (
        <div className="pdf-lightbox-backdrop" onClick={() => setExpanded(false)}>
          <div className="pdf-lightbox" role="dialog" aria-modal="true" aria-label="Source document"
               onClick={(e) => e.stopPropagation()}>
            <div className="pdf-toolbar">
              <button type="button" className="btn btn-sm btn-secondary"
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))} disabled={currentPage <= 1}>
                ← Previous
              </button>
              <span className="mono text-sm">Page {currentPage}{numPages ? ` of ${numPages}` : ""}</span>
              <button type="button" className="btn btn-sm btn-secondary"
                      onClick={() => setCurrentPage((p) => (numPages ? Math.min(numPages, p + 1) : p + 1))}
                      disabled={numPages != null && currentPage >= numPages}>
                Next →
              </button>
              {currentPage !== page && (
                <button type="button" className="btn btn-sm btn-ghost" onClick={() => setCurrentPage(page)}>
                  Back to highlighted page
                </button>
              )}
              <span className="spacer" />
              <button type="button" ref={closeRef} className="btn btn-sm btn-secondary"
                      onClick={() => setExpanded(false)}>
                Close
              </button>
            </div>
            <div className="pdf-lightbox-body">
              <PdfCanvas
                documentSha256={documentSha256}
                page={currentPage}
                region={currentPage === page ? region : null}
                scale={2.2}
                onNumPages={setNumPages}
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
