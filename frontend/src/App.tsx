import { OCRPanel } from "./components/OCRPanel";
import { DeleteDialog } from "./components/DeleteDialog";
import type { DeleteTarget } from "./components/DeleteDialog";
import { useEffect, useRef, useState } from "react";
import {
  Folder,
  FileText,
  Plus,
  Search,
  LoaderCircle,
  Settings2,
  ArrowRight,
  X,
} from "lucide-react";
import { useLanguage, LanguageSelector } from "./i18n";
import { api } from "./api/client";
import { useDocuments } from "./hooks/useDocuments";
import { Button } from "./components/ui/button";
import { ImportDialog } from "./components/ImportDialog";
import { SourceViewer } from "./components/SourceViewer";
import { SearchAssessment } from "./components/SearchAssessment";
import { ManageDialog } from "./components/ManageDialog";
import type { ManagementAction } from "./components/ManageDialog";
import type { Dossier, Hit, SearchResponse, SearchMode, Selection } from "./types";
export default function App() {
  const { t } = useLanguage();
  const ocrWorkspace = "__ocr_workspace__";
  const ocrDocuments = useDocuments(ocrWorkspace);
  const [tab, setTab] = useState<"search" | "ocr">("search");
  const [deleting, setDeleting] = useState<DeleteTarget | null>(null);
  const [dossiers, setDossiers] = useState<Dossier[]>([]);
  const [dossier, setDossier] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [error, setError] = useState("");
  const [question, setQuestion] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("semantic");
  const [searchDocuments, setSearchDocuments] = useState<string[]>([]);
  const [submitted, setSubmitted] = useState("");
  const [analysis, setAnalysis] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [importing, setImporting] = useState(false);
  const [management, setManagement] = useState<ManagementAction | null>(null);
  const [archived, setArchived] = useState(false);
  const [filter, setFilter] = useState("");
  const controller = useRef<AbortController | null>(null);
  const {
    documents,
    error: documentError,
    loading: documentsLoading,
    reload,
  } = useDocuments(dossier);
  const active = dossiers.find((d) => d.dossier_id === dossier);
  const pending = documents.filter((d) =>
    ["queued", "running"].includes(d.status),
  );
  function clearSearch() {
    controller.current?.abort();
    setQuestion("");
    setSearchDocuments([]);
    setSubmitted("");
    setAnalysis(null);
    setSelection(null);
    setSearching(false);
    setError("");
  }
  function changeDossier(id: string) {
    clearSearch();
    setDossier(id);
    setFilter("");
  }
  async function loadCatalog(selected?: string) {
    setCatalogLoading(true);
    try {
      const data = await api.dossiers();
      setDossiers(data);
      setDossier(
        (old) =>
          selected ||
          (data.some((d) => d.dossier_id === old)
            ? old
            : data.find((d) => !d.archived)?.dossier_id || ""),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCatalogLoading(false);
    }
  }
  useEffect(() => {
    void loadCatalog();
    return () => controller.current?.abort();
  }, []);
  async function changed(id?: string) {
    clearSearch();
    await loadCatalog(id);
    if (!id) await reload();
  }
  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || !active || active.archived) return;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setSearching(true);
    setAnalysis(null);
    setError("");
    setSubmitted(question.trim());
    try {
      const result = await api.search(dossier, question.trim(), request.signal, searchMode, searchDocuments.length ? searchDocuments : null);
      if (!request.signal.aborted) setAnalysis(result);
    } catch (e) {
      if (!request.signal.aborted) setError((e as Error).message);
    } finally {
      if (!request.signal.aborted) setSearching(false);
    }
  }
  async function retryDocument(document: string) {
    try {
      await api.retryDocument(dossier, document);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function open(hit: Hit) {
    setSelection({
      document_id: hit.document_id,
      name: hit.name,
      page: hit.page_start || 1,
      text: hit.text,
    });
  }
  return (
    <div className="desk">
      <aside className="work-sidebar" aria-label={t("Dossiers et documents")}>
        <div className="desk-brand">
          Sillage <span>SPOC</span>
        </div>
        <Button onClick={() => setManagement({ kind: "create" })}>
          <Plus size={17} />
          {t("Nouveau dossier")}
        </Button>
        <div className="folder-heading">
          <h2>{t("Dossiers")}</h2>
          <label>
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) => setArchived(e.target.checked)}
            />
            {t("Archivés")}
          </label>
        </div>
        {catalogLoading && (
          <p className="muted" role="status">
            {t("Chargement…")}
          </p>
        )}
        <nav className="folder-list" aria-label={t("Dossiers")}>
          {dossiers
            .filter((d) => !!d.archived === archived)
            .map((d) => (
              <div
                className={`folder-row ${dossier === d.dossier_id ? "active" : ""}`}
                key={d.dossier_id}
              >
                <button
                  onClick={() => changeDossier(d.dossier_id)}
                  aria-current={dossier === d.dossier_id ? "true" : undefined}
                >
                  <Folder size={17} />
                  <span dir="auto">{d.title}</span>
                </button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`${t("Gérer le dossier")} : ${d.title}`}
                  onClick={() => setManagement({ kind: "dossier", dossier: d })}
                >
                  <Settings2 size={16} />
                </Button>
              </div>
            ))}
          {!catalogLoading &&
            !dossiers.some((d) => !!d.archived === archived) && (
              <p className="muted">{t("Aucun dossier")}</p>
            )}
        </nav>
        {active && (
          <section className="work-documents" aria-label={t("Documents")}>
            <div className="folder-heading">
              <h2>{t("Documents")}</h2>
              <span>{documents.length}</span>
            </div>
            {!active.archived && (
              <Button variant="outline" onClick={() => setImporting(true)}>
                <Plus size={16} />
                {t("Ajouter des documents")}
              </Button>
            )}
            {documents.length > 6 && (
              <input
                className="document-find"
                aria-label={t("Filtrer les documents")}
                placeholder={t("Retrouver un document…")}
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            )}
            {documentsLoading && (
              <p role="status" className="muted">
                {t("Chargement des documents…")}
              </p>
            )}
            {documentError && (
              <p role="alert" className="error-message">
                {t(documentError)}
              </p>
            )}
            <div className="work-document-list">
              {documents
                .slice()
                .sort((a, b) => Number(b.has_pdf) - Number(a.has_pdf))
                .filter((d) =>
                  d.name
                    .toLocaleLowerCase()
                    .includes(filter.toLocaleLowerCase()),
                )
                .map((doc) => (
                  <div
                    key={doc.document_id}
                    className={`work-document ${selection?.document_id === doc.document_id ? "selected" : ""}`}
                  >
                    <button
                      className="work-document-open"
                      onClick={() =>
                        setSelection({
                          document_id: doc.document_id,
                          name: doc.name,
                          page: 1,
                        })
                      }
                    >
                      <FileText size={17} />
                      <span>
                        <strong dir="auto">
                          {doc.name}
                          {doc.ocr && <small> · OCR</small>}
                        </strong>
                        <small>
                          {t(
                            {
                              done: "Disponible",
                              review: "OCR à vérifier",
                              running: "En traitement",
                              queued: "En attente",
                              error: "Échec — Réessayer",
                              not_indexed: "Non indexé",
                            }[doc.status],
                          )}
                        </small>
                      </span>
                    </button>
                    {["running", "queued"].includes(doc.status) ? (
                      <p className="muted" role="status">
                        {t(doc.job?.stage || "En attente")}
                      </p>
                    ) : (
                      !active.archived && (
                        <div className="document-tools">
                          <button
                            onClick={() =>
                              setManagement({ kind: "move", document: doc })
                            }
                          >
                            {t("Déplacer")}
                          </button>
                          {doc.has_pdf &&
                            ["error", "not_indexed"].includes(doc.status) && (
                              <button
                                onClick={() => {
                                  void retryDocument(doc.document_id);
                                }}
                              >
                                {t("Réessayer")}
                              </button>
                            )}
                        </div>
                      )
                    )}
                    <button
                      className="delete-document danger-text"
                      onClick={() =>
                        setDeleting({
                          dossier,
                          document: doc.document_id,
                          name: doc.name,
                        })
                      }
                    >
                      {t("Supprimer")}
                    </button>
                    {(doc.job?.error || doc.job?.warning) && (
                      <details>
                        <summary>{t("Détails")}</summary>
                        <p>{t(doc.job.error || doc.job.warning || "")}</p>
                      </details>
                    )}
                  </div>
                ))}
            </div>
          </section>
        )}
        <div className="desk-language">
          <LanguageSelector />
        </div>
      </aside>
      <main className="desk-search">
        <header className="desk-heading">
          <h1 dir="auto">
            {tab === "ocr"
              ? t("Espace OCR indépendant")
              : active?.title || t("Choisissez un dossier")}
          </h1>
          {active?.archived && <span>{t("Archivé")}</span>}
        </header>
        <nav className="ocr-actions" aria-label={t("Outils")}>
          <Button
            variant={tab === "search" ? "default" : "outline"}
            onClick={() => setTab("search")}
          >
            {t("Rechercher")}
          </Button>
          <Button
            variant={tab === "ocr" ? "default" : "outline"}
            onClick={() => setTab("ocr")}
          >
            OCR
          </Button>
        </nav>
        <div hidden={tab !== "ocr"}>
          {ocrDocuments.error ? (
            <p role="alert">
              {t(
                "L’espace OCR n’est pas encore disponible sur le serveur. Rechargez l’interface après son redémarrage.",
              )}
            </p>
          ) : (
            <OCRPanel
              dossier={ocrWorkspace}
              dossiers={dossiers}
              documents={ocrDocuments.documents}
              reload={ocrDocuments.reload}
              onPublished={(id) => {
                changeDossier(id);
                setTab("search");
              }}
              onOpen={(s) => setSelection({ ...s, dossier_id: ocrWorkspace })}
            />
          )}
          {active && documents.some((d) => d.ocr) && (
            <details>
              <summary>{t("Anciennes transcriptions de ce dossier")}</summary>
              <OCRPanel
                key={dossier}
                uploadAllowed={false}
                dossier={dossier}
                dossiers={dossiers}
                documents={documents}
                reload={reload}
                onPublished={(id) => {
                  changeDossier(id);
                  setTab("search");
                }}
                onOpen={setSelection}
              />
            </details>
          )}
        </div>
        <div hidden={tab !== "search"}>
          <form
            onSubmit={(e) => {
              void search(e);
            }}
            className="desk-search-form"
          >
            <label htmlFor="question">
              {t("Votre question sur ce dossier")}
            </label>
            <textarea
              id="question"
              dir="auto"
              rows={3}
              maxLength={2000}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={t("Écrivez votre question…")}
              disabled={!active || active.archived}
            />
            <div className="search-options">
              <label htmlFor="search-mode">{t("Mode de recherche")}</label>
              <select id="search-mode" value={searchMode}
                disabled={searching || !active || active.archived}
                onChange={(e) => setSearchMode(e.target.value as SearchMode)}>
                <option value="semantic">{t("Sémantique")}</option>
                <option value="hybrid">{t("Hybride")}</option>
                <option value="exact">{t("Exacte")}</option>
              </select>
              <p className="muted">{t("Hybride : sens et mots précis. Exacte : suite de mots, sans distinction de casse ni d’accents.")}</p>
              <details>
                <summary>{t("Limiter aux documents sélectionnés")} ({searchDocuments.length})</summary>
                <p className="muted">{t("Sans sélection, tout le dossier est recherché.")}</p>
                <div className="search-document-options">
                  {documents.filter((d) => d.status === "done").map((d) => (
                    <label key={d.document_id}>
                      <input type="checkbox" checked={searchDocuments.includes(d.document_id)}
                        disabled={searching || !active || active.archived}
                        onChange={(e) => setSearchDocuments((old) => e.target.checked
                          ? [...old, d.document_id] : old.filter((id) => id !== d.document_id))} />
                      {d.name}
                    </label>
                  ))}
                </div>
              </details>
            </div>
            <Button
              type="submit"
              disabled={
                !question.trim() || searching || !active || active.archived
              }
            >
              {searching ? (
                <LoaderCircle size={17} className="spin" />
              ) : (
                <Search size={17} />
              )}{" "}
              {t(searching ? "Recherche en cours…" : "Rechercher")}
            </Button>
          </form>
          {error && (
            <div className="error-message" role="alert">
              {t(error)}
              <Button
                variant="ghost"
                onClick={() => {
                  if (!active) void loadCatalog();
                  else setError("");
                }}
              >
                {t("Fermer")}
              </Button>
            </div>
          )}
          {active?.archived ? (
            <p className="desk-empty">
              {t(
                "Restaurez ce dossier pour ajouter des documents ou lancer une recherche.",
              )}
            </p>
          ) : !active ? (
            <p className="desk-empty">
              {t("Choisissez un dossier ou créez-en un pour commencer.")}
            </p>
          ) : !documents.length && !documentsLoading ? (
            <div className="desk-empty">
              <p>{t("Ajoutez des documents pour commencer.")}</p>
              <Button variant="outline" onClick={() => setImporting(true)}>
                {t("Ajouter des documents")}
              </Button>
            </div>
          ) : null}
          {pending.length > 0 && (
            <p className="processing-note" role="status">
              <LoaderCircle className="spin" size={15} />
              {pending.length} {t("documents en traitement")}
            </p>
          )}
          {searching && (
            <p role="status" className="desk-empty">
              {t("Recherche et analyse des passages par Qwen…")}
            </p>
          )}
          {analysis && (
            <section
              aria-label={t("Résultats de recherche")}
              className="desk-results"
            >
              <p className="submitted" dir="auto">
                {submitted}
              </p>
              <SearchAssessment analysis={analysis} onOpen={open} />
              {analysis.results.map((hit, index) => (
                <article
                  key={hit.passage_id}
                  className={`desk-result ${selection?.text === hit.text ? "selected" : ""}`}
                >
                  <div className="result-source">
                    <span>{index + 1}</span>
                    <span dir="auto">{hit.name}</span>
                    {hit.page_start && (
                      <small>
                        {t("Page")} {hit.page_start}
                        {hit.page_end !== hit.page_start
                          ? `–${hit.page_end}`
                          : ""}
                      </small>
                    )}
                  </div>
                  <h2 dir="auto">{hit.title}</h2>
                  {hit.relevance && (
                    <span className={`relevance relevance-${hit.relevance}`}>
                      {t(
                        {
                          direct: "Répond directement",
                          partial: "Répond partiellement",
                          context: "Apporte du contexte",
                          unrelated: "Proximité thématique",
                        }[hit.relevance],
                      )}
                    </span>
                  )}
                  <p className="passage-text" dir="auto">
                    {hit.text}
                  </p>
                  <Button variant="outline" onClick={() => open(hit)}>
                    {t("Voir dans le document")}
                    <ArrowRight size={15} />
                  </Button>
                  <details>
                    <summary>{t("Détails de la recherche")}</summary>
                    <p>
                      {hit.score_kind === "rrf" ? t("Score hybride") : hit.score_kind === "lexical" ? t("Score lexical") : t("Similarité")} : {hit.score.toFixed(3)}
                    </p>
                    <p dir="auto">{hit.relevance_reason}</p>
                  </details>
                </article>
              ))}
              {!analysis.results.length && (
                <p className="desk-empty">
                  {t("Aucun passage retrouvé")} —{" "}
                  {t(
                    "Vérifiez que les documents sont indexés, ou essayez une autre formulation.",
                  )}
                </p>
              )}
            </section>
          )}
        </div>
      </main>
      <SourceViewer
        dossier={selection?.dossier_id || dossier}
        selection={selection}
        onClose={() => setSelection(null)}
      />
      {selection && (
        <button
          className="desk-backdrop"
          aria-label={t("Fermer la source")}
          onClick={() => setSelection(null)}
        >
          <X />
        </button>
      )}
      {importing && active && (
        <ImportDialog
          dossier={dossier}
          title={active.title}
          onClose={() => setImporting(false)}
          onImported={reload}
        />
      )}
      {management && (
        <ManageDialog
          key={management.kind}
          action={management}
          dossier={dossier}
          dossiers={dossiers}
          onDelete={() => {
            if (management.kind === "dossier") {
              setDeleting({
                dossier: management.dossier.dossier_id,
                name: management.dossier.title,
              });
              setManagement(null);
            }
          }}
          onClose={() => setManagement(null)}
          onDone={changed}
        />
      )}
      {deleting && (
        <DeleteDialog
          target={deleting}
          onClose={() => setDeleting(null)}
          onDone={async () => {
            clearSearch();
            if (!deleting.document) {
              setDossier("");
              await loadCatalog();
            } else await reload();
          }}
        />
      )}
    </div>
  );
}
