import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  Clock3,
  FileText,
  FolderClosed,
  Layers3,
  LoaderCircle,
  Plus,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { api } from "./api/client";
import { useDocuments } from "./hooks/useDocuments";
import type { Dossier, Hit, Selection, Status } from "./types";
import { Button } from "./components/ui/button";
import { ImportDialog } from "./components/ImportDialog";
import { SourceViewer } from "./components/SourceViewer";
const statuses: Record<Status, string> = {
  queued: "En attente",
  running: "En cours",
  done: "Indexé",
  error: "Erreur",
  not_indexed: "Non indexé",
};
function StatusIcon({ status }: { status: Status }) {
  if (status === "running") return <LoaderCircle size={13} className="spin" />;
  if (status === "done") return <Check size={13} />;
  if (status === "error") return <AlertCircle size={13} />;
  return <Clock3 size={13} />;
}
export default function App() {
  const [dossiers, setDossiers] = useState<Dossier[]>([]);
  const [dossier, setDossier] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [question, setQuestion] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");
  const [selection, setSelection] = useState<Selection | null>(null);
  const [importing, setImporting] = useState(false);
  const [documentFilter, setDocumentFilter] = useState("");
  const [showDocuments, setShowDocuments] = useState(true);
  const controller = useRef<AbortController | null>(null);
  const {
    documents,
    error: documentError,
    loading: documentsLoading,
    reload,
  } = useDocuments(dossier);
  const active = dossiers.find((d) => d.dossier_id === dossier);
  async function loadCatalog() {
    setCatalogLoading(true);
    setCatalogError("");
    try {
      const data = await api.dossiers();
      setDossiers(data);
      setDossier((id) =>
        data.some((d) => d.dossier_id === id) ? id : data[0]?.dossier_id || "",
      );
    } catch (e) {
      setCatalogError((e as Error).message);
    } finally {
      setCatalogLoading(false);
    }
  }
  useEffect(() => {
    void loadCatalog();
    return () => controller.current?.abort();
  }, []);
  function changeDossier(id: string) {
    controller.current?.abort();
    setDossier(id);
    setQuestion("");
    setSubmitted("");
    setHits([]);
    setSelection(null);
    setError("");
    setSearched(false);
    setSearching(false);
    setDocumentFilter("");
    setImporting(false);
  }
  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (!dossier || !question.trim()) return;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setSearching(true);
    setError("");
    setSelection(null);
    setHits([]);
    setSubmitted(question);
    try {
      const data = await api.search(dossier, question.trim(), request.signal);
      if (!request.signal.aborted) {
        setHits(data.results);
        setSearched(true);
      }
    } catch (e) {
      if (!request.signal.aborted) setError((e as Error).message);
    } finally {
      if (!request.signal.aborted) setSearching(false);
    }
  }
  const displayedDocuments = [...documents]
    .sort((a, b) => Number(b.has_pdf) - Number(a.has_pdf))
    .filter((d) =>
      `${d.name} ${d.document_id}`
        .toLocaleLowerCase("fr")
        .includes(documentFilter.toLocaleLowerCase("fr")),
    );
  const pending = documents.filter(
    (d) => d.status === "running" || d.status === "queued",
  );
  const ready = documents.filter((d) => d.status === "done").length;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="Sillage, accueil">
          <span className="brand-mark">
            <Layers3 size={24} strokeWidth={1.7} />
          </span>
          <span>
            Sillage<small>RECHERCHE DOCUMENTAIRE</small>
          </span>
        </a>
        <div className="workspace-label">
          <span className="workspace-dot" /> Espace d’investigation
        </div>
        <div className="sidebar-section-label">VOTRE ESPACE</div>
        <div className="nav-current">
          <Search size={17} /> Recherche documentaire
          <ChevronRight size={14} />
        </div>
        <div className="dossier-select">
          <label htmlFor="dossier">DOSSIER ACTIF</label>
          <div className="select-wrapper">
            <FolderClosed size={17} />
            <select
              id="dossier"
              aria-label="Dossier actif"
              value={dossier}
              disabled={catalogLoading || !dossiers.length}
              onChange={(e) => changeDossier(e.target.value)}
            >
              {!dossiers.length && (
                <option>
                  {catalogLoading ? "Chargement…" : "Aucun dossier"}
                </option>
              )}
              {dossiers.map((d) => (
                <option key={d.dossier_id} value={d.dossier_id}>
                  {d.title}
                </option>
              ))}
            </select>
            <ChevronDown size={14} />
          </div>
          <span className="dossier-code">{dossier || "Catalogue local"}</span>
        </div>
        <div className="documents-heading">
          <button
            onClick={() => setShowDocuments((v) => !v)}
            aria-expanded={showDocuments}
          >
            <ChevronDown
              size={14}
              className={showDocuments ? "" : "collapsed"}
            />{" "}
            Documents <span>{documents.length}</span>
          </button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setImporting(true)}
            disabled={!dossier}
            aria-label="Importer un PDF"
          >
            <Plus size={16} />
          </Button>
        </div>
        {showDocuments && (
          <>
            <div className="document-filter">
              <Search size={14} />
              <input
                aria-label="Filtrer les documents"
                placeholder="Retrouver un document…"
                value={documentFilter}
                onChange={(e) => setDocumentFilter(e.target.value)}
              />
            </div>
            <div className="document-list" aria-live="polite">
              {documentsLoading && (
                <p className="list-message">Chargement des documents…</p>
              )}
              {documentError && (
                <p className="error-message">{documentError}</p>
              )}
              {!documentsLoading &&
                !documentError &&
                !displayedDocuments.length && (
                  <p className="list-message">
                    {documents.length
                      ? "Aucun document correspondant."
                      : "Aucun document dans ce dossier."}
                  </p>
                )}
              {displayedDocuments.map((doc) => (
                <div
                  key={doc.document_id}
                  className={`document-item ${selection?.document_id === doc.document_id ? "document-selected" : ""}`}
                >
                  <button
                    onClick={() =>
                      setSelection({
                        document_id: doc.document_id,
                        name: doc.name,
                        page: 1,
                      })
                    }
                    className="document-open"
                  >
                    <FileText size={18} strokeWidth={1.6} />
                    <span>
                      <strong title={doc.name}>{doc.name}</strong>
                      <small>
                        <span className={`status status-${doc.status}`}>
                          <StatusIcon status={doc.status} />
                          {statuses[doc.status]}
                        </span>
                        {doc.job?.page_count
                          ? ` · ${doc.job.page_count} p.`
                          : ` · ${doc.has_pdf ? "PDF" : "Texte"}`}
                      </small>
                    </span>
                  </button>
                  {doc.job?.status === "running" && (
                    <p className="job-stage">{doc.job.stage}</p>
                  )}
                  {doc.job?.error && (
                    <p className="job-error">{doc.job.error}</p>
                  )}
                  {doc.job?.warning && (
                    <p className="job-warning">{doc.job.warning}</p>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
        <div className="sidebar-bottom">
          <Button
            variant="outline"
            onClick={() => setImporting(true)}
            disabled={!dossier}
            className="import-button"
          >
            <Plus size={17} /> Importer un document
          </Button>
          <div className="prototype">
            <ShieldCheck size={15} />
            <span>
              Prototype de recherche<small>Données fictives ou publiques</small>
            </span>
            <span className="version">V1</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <FolderClosed size={15} />
            <span>Dossiers</span>
            <ChevronRight size={13} />
            <strong>{dossier || "Sélection"}</strong>
            <ChevronRight size={13} />
            <span>Recherche</span>
          </div>
          <span className="local-badge">
            <span /> Exécution locale
          </span>
        </header>
        <div className="workspace">
          <main className="search-panel">
            <div className="page-heading">
              <span className="eyebrow">EXPLORER LE DOSSIER</span>
              <span className="case-badge">
                <FolderClosed size={13} />
                {dossier || "—"}
              </span>
            </div>
            <h1>
              {searched || searching ? (
                "Recherche documentaire"
              ) : (
                <>
                  Une question.
                  <br />
                  <span>Les sources pour y répondre.</span>
                </>
              )}
            </h1>
            <p className="intro">
              Retrouvez les passages utiles dans les pièces de votre dossier.
              <br className="desktop-break" /> Consultez le texte original et
              vérifiez sa provenance.
            </p>
            <form
              onSubmit={(e) => {
                void search(e);
              }}
              className="search-form"
            >
              <Search size={22} strokeWidth={1.7} />
              <input
                aria-label="Question de recherche"
                value={question}
                maxLength={2000}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Que cherchez-vous dans ce dossier ?"
                disabled={!dossier}
              />
              <Button
                type="submit"
                disabled={searching || !dossier || !question.trim()}
                aria-label="Rechercher dans ce dossier"
              >
                {searching ? (
                  <LoaderCircle size={18} className="spin" />
                ) : (
                  <ArrowRight size={19} />
                )}
              </Button>
            </form>
            <div className="scope-note">
              <ShieldCheck size={13} /> Recherche limitée au dossier sélectionné
              <span>Texte original · Sources vérifiables</span>
            </div>
            {catalogError && (
              <div className="error-message" role="alert">
                <AlertCircle size={17} />
                <span>{catalogError}</span>
                <Button
                  variant="outline"
                  onClick={() => {
                    void loadCatalog();
                  }}
                >
                  Réessayer
                </Button>
              </div>
            )}
            {error && (
              <div className="error-message" role="alert">
                <AlertCircle size={17} />
                {error}
              </div>
            )}
            {pending.length > 0 && (
              <div className="processing-banner" role="status">
                <LoaderCircle className="spin" size={17} />
                <div>
                  <strong>
                    {pending.length} document{pending.length > 1 ? "s" : ""} en
                    traitement
                  </strong>
                  <span>
                    {pending.find((d) => d.status === "running")?.job?.stage ||
                      "En attente de traitement"}{" "}
                    · Suivi dans la liste des documents
                  </span>
                </div>
              </div>
            )}
            {searching ? (
              <div className="results-loading" role="status">
                <LoaderCircle size={25} className="spin" />
                <h2>Recherche dans votre dossier…</h2>
                <p>Comparaison de votre question avec les extraits indexés.</p>
              </div>
            ) : searched ? (
              <section className="results" aria-label="Résultats de recherche">
                <div className="results-heading">
                  <h2>
                    {hits.length} passage{hits.length > 1 ? "s" : ""} retrouvé
                    {hits.length > 1 ? "s" : ""}
                  </h2>
                  <span>PAR SIMILARITÉ</span>
                </div>
                <p className="query-label">Pour « {submitted} »</p>
                {hits.length ? (
                  hits.map((hit, index) => (
                    <article
                      key={hit.passage_id}
                      className={`result-card ${selection?.document_id === hit.document_id && selection?.text === hit.text ? "result-selected" : ""}`}
                    >
                      <div className="result-top">
                        <span className="result-number">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <span className="result-document">
                          <FileText size={13} />
                          {hit.name}
                        </span>
                        {hit.page_start && (
                          <span className="page-tag">
                            p. {hit.page_start}
                            {hit.page_end !== hit.page_start
                              ? `–${hit.page_end}`
                              : ""}
                          </span>
                        )}
                      </div>
                      <h3>{hit.title}</h3>
                      <p className="passage-text">{hit.text}</p>
                      <div className="result-footer">
                        <span title="Similarité cosinus ; ce score n’est pas une probabilité de vérité.">
                          Similarité {hit.score.toFixed(3)}
                        </span>
                        <Button
                          variant="ghost"
                          onClick={() =>
                            setSelection({
                              document_id: hit.document_id,
                              name: hit.name,
                              page: hit.page_start || 1,
                              text: hit.text,
                            })
                          }
                        >
                          Consulter la source <ArrowUpRight size={15} />
                        </Button>
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="empty-results">
                    <FileText size={30} />
                    <h3>Aucun passage retrouvé</h3>
                    <p>
                      Vérifiez que les documents sont indexés, ou essayez une
                      autre formulation.
                    </p>
                  </div>
                )}
                <p className="results-note">
                  La similarité indique une proximité de sens. Elle ne confirme
                  pas les faits rapportés.
                </p>
              </section>
            ) : (
              !error && (
                <section className="welcome-section">
                  <div className="welcome-heading">
                    <BookOpen size={18} />
                    <h2>Votre dossier, avec son contexte.</h2>
                  </div>
                  <p>
                    Interrogez les documents en langage naturel. Les passages
                    retrouvés conservent les témoignages, les réserves et les
                    rectifications de leur source.
                  </p>
                  <div className="workspace-stats">
                    <div>
                      <strong>
                        {documents.length.toString().padStart(2, "0")}
                      </strong>
                      <span>documents au dossier</span>
                    </div>
                    <div>
                      <strong>{ready.toString().padStart(2, "0")}</strong>
                      <span>documents indexés</span>
                    </div>
                    <div>
                      <strong>
                        {active?.person_ids.length
                          .toString()
                          .padStart(2, "0") || "00"}
                      </strong>
                      <span>personnes associées</span>
                    </div>
                  </div>
                  <div className="how-it-works">
                    <div>
                      <span>01</span>
                      <strong>Choisissez votre dossier</strong>
                      <p>Un périmètre explicite pour chaque recherche.</p>
                    </div>
                    <div>
                      <span>02</span>
                      <strong>Posez votre question</strong>
                      <p>Retrouvez les extraits proches de votre demande.</p>
                    </div>
                    <div>
                      <span>03</span>
                      <strong>Vérifiez la source</strong>
                      <p>Revenez au document et à la page d’origine.</p>
                    </div>
                  </div>
                </section>
              )
            )}
            <footer className="main-footer">
              <span>SILLAGE / SPOC</span>
              <span>Recherche documentaire · Version de démonstration</span>
            </footer>
          </main>
          <SourceViewer
            dossier={dossier}
            selection={selection}
            onClose={() => setSelection(null)}
          />
          {selection && (
            <button
              className="mobile-source-backdrop"
              aria-label="Fermer la source"
              onClick={() => setSelection(null)}
            >
              <X />
            </button>
          )}
        </div>
      </div>
      {importing && active && (
        <ImportDialog
          dossier={dossier}
          title={active.title}
          onClose={() => setImporting(false)}
          onImported={reload}
        />
      )}
    </div>
  );
}
