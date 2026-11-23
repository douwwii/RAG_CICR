import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import {
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  FileSearch,
  LoaderCircle,
  Minus,
  Plus,
  X,
} from "lucide-react";
import { api } from "../api/client";
import type { Selection, Source } from "../types";
import { Button } from "./ui/button";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export function SourceViewer({
  dossier,
  selection,
  onClose,
}: {
  dossier: string;
  selection: Selection | null;
  onClose: () => void;
}) {
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [width, setWidth] = useState(400);
  const [zoom, setZoom] = useState(1);
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setSource(null);
    setError("");
    setPages(0);
    setPage(selection?.page || 1);
    setZoom(1);
    if (!selection) return;
    const controller = new AbortController();
    void api
      .source(dossier, selection.document_id, controller.signal)
      .then(setSource)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [dossier, selection]);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(180, entries[0].contentRect.width - 32)),
    );
    observer.observe(container.current);
    return () => observer.disconnect();
  }, [selection?.document_id]);
  return (
    <aside
      className={`source-panel ${selection ? "source-open" : ""}`}
      aria-label="Document source"
    >
      <div className="panel-heading">
        <div className="eyebrow">DOCUMENT SOURCE</div>
        {selection && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Fermer la source"
          >
            <X size={17} />
          </Button>
        )}
      </div>
      {selection ? (
        <>
          <div className="source-title">
            <span className="file-square">
              <FileSearch size={20} />
            </span>
            <div>
              <h2>{selection.name}</h2>
              <p>
                {source?.kind === "pdf"
                  ? "Document original · PDF"
                  : "Consultation de la source"}
              </p>
            </div>
          </div>
          {source?.kind === "pdf" && (
            <div className="pdf-toolbar">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                aria-label="Page précédente"
              >
                <ChevronLeft size={17} />
              </Button>
              <span>
                Page <strong>{page}</strong> / {pages || "…"}
              </span>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                disabled={!pages || page >= pages}
                aria-label="Page suivante"
              >
                <ChevronRight size={17} />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setZoom((z) => Math.max(1, z - 0.25))}
                disabled={zoom <= 1}
                aria-label="Réduire le zoom"
              >
                <Minus size={14} />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setZoom((z) => Math.min(2.5, z + 0.25))}
                disabled={zoom >= 2.5}
                aria-label="Agrandir la page"
              >
                <Plus size={14} />
              </Button>
              <Button variant="ghost" size="icon" asChild>
                <a
                  href={
                    api.file(dossier, selection.document_id) + `#page=${page}`
                  }
                  target="_blank"
                  rel="noreferrer"
                  aria-label="Ouvrir le PDF dans un nouvel onglet"
                >
                  <ArrowUpRight size={17} />
                </a>
              </Button>
            </div>
          )}
          <div className="source-content" ref={container}>
            {error && (
              <div className="error-message" role="alert">
                {error}
              </div>
            )}
            {!source && !error && (
              <div className="loading">
                <LoaderCircle className="spin" size={20} /> Ouverture de la
                source…
              </div>
            )}
            {source?.kind === "pdf" && (
              <Document
                file={api.file(dossier, selection.document_id)}
                onLoadSuccess={({ numPages }) => {
                  setPages(numPages);
                  setPage((p) => Math.min(p, numPages));
                }}
                onLoadError={() =>
                  setError(
                    "Impossible de lire ce PDF. Vous pouvez essayer de l’ouvrir dans un nouvel onglet.",
                  )
                }
                loading={
                  <div className="loading">
                    <LoaderCircle className="spin" size={20} /> Chargement du
                    PDF…
                  </div>
                }
              >
                <Page
                  pageNumber={page}
                  width={width * zoom}
                  loading={
                    <div className="loading">Chargement de la page…</div>
                  }
                />
              </Document>
            )}
            {source?.kind === "text" && (
              <div className="text-source">
                <span className="eyebrow">TEXTE ORIGINAL</span>
                <pre>{source.text}</pre>
                <p className="muted">
                  Cette source ne possède pas de PDF associé.
                </p>
              </div>
            )}
          </div>
          {selection.text && (
            <div className="source-excerpt">
              <span className="eyebrow">PASSAGE SÉLECTIONNÉ</span>
              <p>{selection.text}</p>
            </div>
          )}
        </>
      ) : (
        <div className="source-placeholder">
          <div className="document-illustration">
            <FileSearch size={36} strokeWidth={1.2} />
            <span />
            <span />
            <span />
          </div>
          <h2>Remontez à la source.</h2>
          <p>
            Sélectionnez un passage pour consulter son document original et
            vérifier son contexte.
          </p>
          <div className="source-note">
            Chaque résultat reste relié à sa source.
          </div>
        </div>
      )}
    </aside>
  );
}
