import { useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { BACKEND_URL } from "./api";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const SCALE = 1.5;

// satyapramana.md's own stated demo axiom: click a verdict, land on the
// exact highlighted line of the actual source PDF. `region` is
// [x0, top, x1, bottom] in PDF points, already top-down (pdfplumber's own
// convention -- the same one the extraction pipeline records with) -- which
// is also how a canvas is addressed, so no extra Y-flip is needed, only the
// same scale factor used to render the page.
export default function PdfEvidenceViewer({ documentSha256, page, region }) {
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
        const pdfPage = await doc.getPage(page);
        const viewport = pdfPage.getViewport({ scale: SCALE });
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
  }, [documentSha256, page]);

  const [x0, top, x1, bottom] = region;
  const box = {
    position: "absolute",
    left: x0 * SCALE, top: top * SCALE,
    width: (x1 - x0) * SCALE, height: (bottom - top) * SCALE,
    border: "2px solid var(--status-fail-fg)", background: "var(--highlight-overlay-bg)",
    pointerEvents: "none",
  };

  return (
    <div style={{ position: "relative", display: "inline-block", border: "1px solid var(--color-border)", borderRadius: "var(--radius-md)", overflow: "auto", maxWidth: "100%", maxHeight: 500 }}>
      {loading && <p className="hint" style={{ padding: 12 }}>Loading page {page}…</p>}
      {error && <p className="error" style={{ padding: 12 }}>Could not load the source document: {String(error.message || error)}</p>}
      <canvas ref={canvasRef} style={{ display: loading || error ? "none" : "block" }} />
      {pageSize && !loading && !error && <div style={box} />}
    </div>
  );
}
