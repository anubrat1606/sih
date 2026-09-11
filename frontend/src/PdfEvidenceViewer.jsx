import { useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { BACKEND_URL } from "./api";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

// satyapramana.md's own stated demo axiom: click a verdict, land on the
// exact highlighted line of the actual source PDF. `region` is
// [x0, top, x1, bottom] in PDF points, already top-down (pdfplumber's own
// convention -- the same one the extraction pipeline records with) -- which
// is also how a canvas is addressed, so no extra Y-flip is needed, only the
// same scale factor used to render the page. Shared by the inline preview
// and the lightbox below -- same rendering logic, different scale and
// container, never duplicated.
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
        const doc = await pdfjsLib.getDocument(`${BACKEND_URL}/documents/${documentSha256}`).promise;
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onNumPages is a setter, stable identity not required here
  }, [documentSha256, page, scale]);

  const box = region && pageSize && (() => {
    const [x0, top, x1, bottom] = region;
    return {
      position: "absolute",
      left: x0 * scale, top: top * scale,
      width: (x1 - x0) * scale, height: (bottom - top) * scale,
      border: "2px solid var(--status-fail-fg)", background: "var(--highlight-overlay-bg)",
      pointerEvents: "none",
    };
  })();

  return (
    <div className="pdf-canvas-wrap">
      {loading && <p className="hint" style={{ padding: 12 }}>Loading page {page}…</p>}
      {error && <p className="error" style={{ padding: 12 }}>Could not load the source document: {String(error.message || error)}</p>}
      <canvas ref={canvasRef} style={{ display: loading || error ? "none" : "block" }} />
      {box && <div style={box} />}
    </div>
  );
}

export default function PdfEvidenceViewer({ documentSha256, page, region }) {
  const [expanded, setExpanded] = useState(false);
  const [currentPage, setCurrentPage] = useState(page);
  const [numPages, setNumPages] = useState(null);
  const closeButtonRef = useRef(null);

  // A different verdict's trail can reuse this component for a different
  // document/page -- reset to the newly-highlighted page rather than
  // leaving the lightbox pointed at wherever the previous one left off.
  // Adjusted during render (React's own recommended pattern for "reset
  // state when a prop changes"), not in an effect -- an effect here would
  // mean an extra render of the stale page before the reset lands.
  const [trackedKey, setTrackedKey] = useState(`${documentSha256}:${page}`);
  const key = `${documentSha256}:${page}`;
  if (key !== trackedKey) {
    setTrackedKey(key);
    setCurrentPage(page);
  }

  useEffect(() => {
    if (!expanded) return;
    closeButtonRef.current?.focus();
    function onKey(e) {
      if (e.key === "Escape") setExpanded(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [expanded]);

  return (
    <>
      <div className="pdf-inline">
        <PdfCanvas documentSha256={documentSha256} page={page} region={region} scale={1.5} />
        <button type="button" className="pdf-expand" onClick={() => setExpanded(true)}>
          Expand ⤢
        </button>
      </div>

      {expanded && (
        <div className="pdf-lightbox-backdrop" onClick={() => setExpanded(false)}>
          <div className="pdf-lightbox" role="dialog" aria-modal="true" aria-label="Source document"
               onClick={(e) => e.stopPropagation()}>
            <div className="pdf-lightbox-toolbar">
              <button type="button" onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage <= 1}>
                ← Prev page
              </button>
              <span className="mono">Page {currentPage}{numPages ? ` of ${numPages}` : ""}</span>
              <button type="button"
                      onClick={() => setCurrentPage((p) => (numPages ? Math.min(numPages, p + 1) : p + 1))}
                      disabled={numPages != null && currentPage >= numPages}>
                Next page →
              </button>
              {currentPage !== page && (
                <button type="button" onClick={() => setCurrentPage(page)}>Back to highlighted page</button>
              )}
              <button type="button" ref={closeButtonRef} className="pdf-lightbox-close"
                      onClick={() => setExpanded(false)}>
                ✕ Close
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
