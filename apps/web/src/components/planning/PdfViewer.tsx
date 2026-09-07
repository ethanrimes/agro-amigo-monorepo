"use client";
import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
export function PdfViewer({
  id,
  initialPage = 1,
}: {
  id: string;
  initialPage?: number;
}) {
  const host = useRef<HTMLDivElement>(null),
    canvas = useRef<HTMLCanvasElement>(null),
    render = useRef<RenderTask | null>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null),
    [page, setPage] = useState(initialPage),
    [zoom, setZoom] = useState(1),
    [width, setWidth] = useState(600),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [text, setText] = useState("");
  useEffect(() => {
    let live = true;
    let task: ReturnType<
      typeof import("pdfjs-dist/legacy/build/pdf.mjs").getDocument
    > | null = null;
    import("pdfjs-dist/legacy/build/pdf.mjs")
      .then((lib) => {
        if (!live) return;
        lib.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.min.mjs";
        task = lib.getDocument({
          url: "/api/evidence/" + id + "/content",
          standardFontDataUrl: "/pdfjs/standard_fonts/",
          wasmUrl: "/pdfjs/wasm/",
          cMapUrl: "/pdfjs/cmaps/",
          cMapPacked: true,
        });
        return task.promise;
      })
      .then((value) => {
        if (value && live) {
          setPdf(value);
          setPage(Math.max(1, Math.min(initialPage, value.numPages)));
        }
      })
      .catch(() => {
        if (live) {
          setError(
            "No pudimos mostrar el PDF. Puedes descargar el documento original.",
          );
          setLoading(false);
        }
      });
    return () => {
      live = false;
      render.current?.cancel();
      void task?.destroy();
    };
  }, [id, initialPage]);
  useEffect(() => {
    if (!host.current) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(250, entries[0].contentRect.width - 24)),
    );
    observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!pdf) return;
    let active = true;
    setLoading(true);
    setText("");
    const old = render.current;
    old?.cancel();
    (async () => {
      await old?.promise.catch(() => {});
      const p = await pdf.getPage(page);
      if (!active || !canvas.current) return;
      const base = p.getViewport({ scale: 1 }),
        scale = (Math.min(width, 1000) / base.width) * zoom,
        viewport = p.getViewport({ scale }),
        ratio = Math.min(window.devicePixelRatio || 1, 2);
      const el = canvas.current;
      el.width = Math.floor(viewport.width * ratio);
      el.height = Math.floor(viewport.height * ratio);
      el.style.width = viewport.width + "px";
      el.style.height = viewport.height + "px";
      const task = p.render({
        canvas: el,
        viewport,
        transform: [ratio, 0, 0, ratio, 0, 0],
      });
      render.current = task;
      await task.promise;
      // Older WebKit versions do not implement ReadableStream's async iterator,
      // which PDF.js 6 uses in getTextContent(). Read the supported stream API
      // directly so the accessible text works on the iOS client as well.
      const reader = p.streamTextContent().getReader();
      const items: { str: string }[] = [];
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          for (const item of value.items) {
            if ("str" in item) items.push(item);
          }
        }
      } finally {
        reader.releaseLock();
      }
      if (active) {
        setText(items.map((item) => ("str" in item ? item.str : "")).join(" "));
        setLoading(false);
        setError("");
      }
    })().catch((e) => {
      if (active && e.name !== "RenderingCancelledException") {
        console.error("PDF page rendering failed", e);
        setError(
          "No pudimos mostrar esta página. Descarga el PDF para consultarlo.",
        );
        setLoading(false);
      }
    });
    return () => {
      active = false;
      render.current?.cancel();
    };
  }, [pdf, page, zoom, width]);
  return (
    <section className="pdf-viewer" aria-label="Visor del documento original">
      <div className="pdf-toolbar">
        <button
          className="button secondary"
          disabled={!pdf || page <= 1}
          onClick={() => setPage((p) => p - 1)}
        >
          ← Anterior
        </button>
        <label>
          Página{" "}
          <select
            aria-label="Página del documento"
            value={page}
            onChange={(e) => setPage(+e.target.value)}
          >
            {Array.from({ length: pdf?.numPages || 1 }, (_, i) => (
              <option key={i} value={i + 1}>
                {i + 1}
              </option>
            ))}
          </select>{" "}
          de {pdf?.numPages || "…"}
        </label>
        <button
          className="button secondary"
          disabled={!pdf || page >= pdf.numPages}
          onClick={() => setPage((p) => p + 1)}
        >
          Siguiente →
        </button>
        <label className="pdf-zoom">
          Tamaño{" "}
          <select
            aria-label="Tamaño del documento"
            value={zoom}
            onChange={(e) => setZoom(+e.target.value)}
          >
            <option value={1}>Ajustar</option>
            <option value={1.5}>150 %</option>
            <option value={2}>200 %</option>
          </select>
        </label>
      </div>
      {loading && !error && (
        <p role="status" className="pdf-status">
          Cargando página del documento…
        </p>
      )}
      {error && (
        <p role="alert" className="inline-warning">
          {error}
        </p>
      )}
      <div className="pdf-body">
        {pdf && (
          <nav className="pdf-pages" aria-label="Miniaturas de páginas">
            {Array.from(
              { length: Math.min(5, pdf.numPages) },
              (_, i) => Math.max(1, Math.min(page - 2, pdf.numPages - 4)) + i,
            ).map((n) => (
              <button
                type="button"
                key={n}
                className={page === n ? "selected" : ""}
                aria-label={"Ir a página " + n}
                aria-current={page === n ? "page" : undefined}
                onClick={() => setPage(n)}
              >
                <PdfThumbnail pdf={pdf} page={n} />
                <span>Página {n}</span>
              </button>
            ))}
          </nav>
        )}
        <div className="pdf-paper" ref={host}>
          <canvas
            ref={canvas}
            aria-label={"Página " + page + " del PDF"}
            data-rendered={!loading && !error ? "true" : "false"}
          />
        </div>
      </div>
      {text && (
        <details className="source-explanation">
          <summary>Leer el texto de esta página</summary>
          <p className="pdf-text">{text}</p>
        </details>
      )}
    </section>
  );
}

function PdfThumbnail({ pdf, page }: { pdf: PDFDocumentProxy; page: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let active = true,
      task: RenderTask | undefined;
    void pdf
      .getPage(page)
      .then((p) => {
        if (!active || !ref.current) return;
        const base = p.getViewport({ scale: 1 }),
          viewport = p.getViewport({ scale: 96 / base.width }),
          canvas = ref.current;
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        task = p.render({ canvas, viewport });
        return task.promise;
      })
      .catch(() => {});
    return () => {
      active = false;
      task?.cancel();
    };
  }, [pdf, page]);
  return <canvas ref={ref} aria-hidden="true" />;
}
