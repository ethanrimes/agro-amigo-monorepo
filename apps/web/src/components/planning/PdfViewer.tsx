"use client";
import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { pdfCanvasBackingRatio } from "./pdf-canvas-sizing";
type PageIdentity = {
  id: string; initialPage: number; pdf: PDFDocumentProxy;
  page: number; zoom: number; width: number; revision: number;
};
type ReadyPage = PageIdentity & { text: string };
function samePage(a: PageIdentity | null, b: PageIdentity | null): boolean {
  return Boolean(a && b && a.id === b.id && a.initialPage === b.initialPage &&
    a.pdf === b.pdf && a.page === b.page && a.zoom === b.zoom &&
    a.width === b.width && a.revision === b.revision);
}
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
  const [loaded, setLoaded] = useState<{ id: string; initialPage: number; pdf: PDFDocumentProxy } | null>(null),
    [view, setView] = useState({ page: initialPage, zoom: 1, width: 600, revision: 0 }),
    [ready, setReady] = useState<ReadyPage | null>(null),
    [pageFailure, setPageFailure] = useState<(PageIdentity & { message: string }) | null>(null),
    [documentFailure, setDocumentFailure] = useState<{ id: string; initialPage: number; message: string } | null>(null);
  const { page, zoom, width, revision } = view;
  const setPage = (next: number | ((page: number) => number)) => setView((previous) => {
    const page = typeof next === "function" ? next(previous.page) : next;
    return page === previous.page ? previous : { ...previous, page, revision: previous.revision + 1 };
  });
  const setZoom = (zoom: number) => setView((previous) =>
    zoom === previous.zoom ? previous : { ...previous, zoom, revision: previous.revision + 1 });
  const setWidth = (width: number) => setView((previous) =>
    width === previous.width ? previous : { ...previous, width, revision: previous.revision + 1 });
  const pdf = loaded?.id === id && loaded.initialPage === initialPage ? loaded.pdf : null;
  const selectedPage = pdf ? page : initialPage;
  const selected: PageIdentity | null = pdf ? { id, initialPage, pdf, page: selectedPage, zoom, width, revision } : null;
  // State from the preceding page or document must never certify the selected
  // canvas during the commit before its new render effect starts.
  const rendered = samePage(ready, selected);
  const error = samePage(pageFailure, selected) ? pageFailure!.message :
    documentFailure?.id === id && documentFailure.initialPage === initialPage
      ? documentFailure.message : "";
  const loading = !rendered && !error;
  const text = rendered ? ready!.text : "";
  useEffect(() => {
    let live = true;
    setLoaded(null);
    setReady(null);
    setPageFailure(null);
    setDocumentFailure(null);
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
          setLoaded({ id, initialPage, pdf: value });
          setPage(Math.max(1, Math.min(initialPage, value.numPages)));
          setDocumentFailure(null);
        }
      })
      .catch(() => {
        if (live) {
          setDocumentFailure({ id, initialPage,
            message: "No pudimos mostrar el PDF. Puedes descargar el documento original." });
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
    const identity: PageIdentity = { id, initialPage, pdf, page: selectedPage, zoom, width, revision };
    const old = render.current;
    old?.cancel();
    (async () => {
      await old?.promise.catch(() => {});
      const p = await pdf.getPage(selectedPage);
      if (!active || !canvas.current) return;
      const base = p.getViewport({ scale: 1 }),
        scale = (Math.min(width, 1000) / base.width) * zoom,
        viewport = p.getViewport({ scale }),
        ratio = pdfCanvasBackingRatio({
          width: viewport.width, height: viewport.height,
          devicePixelRatio: window.devicePixelRatio,
          userAgent: window.navigator.userAgent,
        });
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
        setReady({ ...identity, text: items.map((item) => ("str" in item ? item.str : "")).join(" ") });
        setPageFailure(null);
      }
    })().catch((e) => {
      if (active && e.name !== "RenderingCancelledException") {
        console.error("PDF page rendering failed", e);
        setPageFailure({ ...identity,
          message: "No pudimos mostrar esta página. Descarga el PDF para consultarlo." });
      }
    });
    return () => {
      active = false;
      render.current?.cancel();
    };
  }, [id, initialPage, pdf, selectedPage, zoom, width, revision]);
  return (
    <section className="pdf-viewer" aria-label="Visor del documento original">
      <div className="pdf-toolbar">
        <button
          className="button secondary"
          disabled={!pdf || selectedPage <= 1}
          onClick={() => setPage((p) => p - 1)}
        >
          ← Anterior
        </button>
        <SearchableSelect
          label="Página del documento"
          value={String(selectedPage)}
          options={Array.from({ length: pdf?.numPages || 0 }, (_, i) => ({
            id: String(i + 1), label: String(i + 1), detail: `de ${pdf?.numPages}`, searchText: String(i + 1),
          }))}
          onChange={(value) => { if (value) setPage(Number(value)); }}
          selectedLabel={`${selectedPage} de ${pdf?.numPages || "…"}`}
          placeholder="Busca el número de página"
          loading={!pdf}
          allowClear={false}
        />
        <button
          className="button secondary"
          disabled={!pdf || selectedPage >= pdf.numPages}
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
          Cargando página {selectedPage} del documento…
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
              (_, i) => Math.max(1, Math.min(selectedPage - 2, pdf.numPages - 4)) + i,
            ).map((n) => (
              <button
                type="button"
                key={n}
                className={selectedPage === n ? "selected" : ""}
                aria-label={"Ir a página " + n}
                aria-current={selectedPage === n ? "page" : undefined}
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
            aria-label={"Página " + selectedPage + " del PDF"}
            aria-busy={loading}
            data-rendered={rendered && !error ? "true" : "false"}
            style={{ visibility: rendered && !error ? "visible" : "hidden" }}
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
