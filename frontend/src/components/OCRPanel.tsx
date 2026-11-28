import { useEffect, useId, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Download,
  FileText,
  FileUp,
  LoaderCircle,
  RotateCcw,
  Save,
  ScanText,
  Search,
} from "lucide-react";
import { api } from "../api/client";
import { useLanguage } from "../i18n";
import type { OCRState, SourceDocument, Selection, Dossier } from "../types";
import { Button } from "./ui/button";

type Action = "upload" | "save" | "publish" | "retry";

export function OCRPanel({
  dossier,
  dossiers,
  documents,
  reload,
  onOpen,
  onPublished,
  uploadAllowed = true,
}: {
  uploadAllowed?: boolean;
  dossiers: Dossier[];
  onPublished: (id: string) => void;
  dossier: string;
  documents: SourceDocument[];
  reload: () => Promise<void>;
  onOpen: (selection: Selection) => void;
}) {
  const { t } = useLanguage();
  const [id, setId] = useState("");
  const [destination, setDestination] = useState("");
  const [state, setState] = useState<OCRState | null>(null);
  const [page, setPage] = useState(0);
  const [pending, setPending] = useState<Action | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const prefix = useId();
  const doc = documents.find(
    (d) => d.dossier_id === dossier && d.document_id === id,
  );
  const busy = pending !== null;
  const working = busy || doc?.status === "queued" || doc?.status === "running";
  const ocrDocuments = documents.filter(
    (d) => d.dossier_id === dossier && d.ocr,
  );

  // Retrouver le traitement actif lors d'un retour à l'onglet ou d'un rechargement.
  useEffect(() => {
    if (!id) {
      const current = documents.find(
        (d) =>
          d.dossier_id === dossier &&
          d.ocr &&
          ["queued", "running", "review", "error"].includes(d.status),
      );
      if (current) setId(current.document_id);
    } else if (
      documents.length &&
      !documents.some(
        (d) => d.dossier_id === dossier && d.document_id === id,
      ) &&
      !busy
    ) {
      setId("");
      setState(null);
    }
  }, [documents, dossier, id, busy]);

  useEffect(() => {
    if (!id) return;
    let active = true;
    setLoading(true);
    api
      .ocr(dossier, id)
      .then((data) => {
        if (active) {
          setState(data);
          setPage((old) => Math.min(old, Math.max(0, data.pages.length - 1)));
        }
      })
      .catch(() => {
        if (active)
          setError(
            t(
              "Impossible de charger la transcription. Sélectionnez à nouveau le document pour réessayer.",
            ),
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [dossier, id, doc?.status, doc?.job?.stage]);

  function mayDiscard() {
    return (
      !dirty ||
      window.confirm(t("Abandonner les corrections non enregistrées ?"))
    );
  }
  function select(value: string) {
    if (!mayDiscard()) return;
    setId(value);
    setState(null);
    setPage(0);
    setDirty(false);
    setError("");
    setNotice("");
  }
  function show(index: number) {
    setPage(index);
    if (doc) onOpen({ document_id: id, name: doc.name, page: index + 1 });
  }
  async function upload() {
    if (!file || !mayDiscard()) return;
    setPending("upload");
    setError("");
    setNotice("");
    try {
      const result = await api.uploadOCR(dossier, file);
      setId(result.job.document_id);
      setState(null);
      setPage(0);
      setDirty(false);
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      setNotice(
        t(
          "Document reçu. Le traitement peut continuer pendant que vous utilisez l’application.",
        ),
      );
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(null);
    }
  }
  async function action(kind: Exclude<Action, "upload">, retryPage?: number) {
    if (kind === "retry" && !mayDiscard()) return;
    setPending(kind);
    setError("");
    setNotice("");
    try {
      const result = await api.editOCR(
        dossier,
        id,
        kind === "retry"
          ? { retry: true, retry_page: retryPage }
          : {
              pages: state?.pages.map((p) => p.transcription),
              publish: kind === "publish",
              destination: kind === "publish" ? destination : undefined,
            },
      );
      setDirty(false);
      setNotice(
        t(
          kind === "save"
            ? "Corrections enregistrées. Ajoutez le document à la recherche lorsque vous avez terminé la vérification."
            : kind === "publish"
              ? "Ajout à la recherche demandé. Le document sera disponible à la fin du traitement."
              : "Nouvelle lecture demandée. Les pages déjà terminées sont conservées.",
        ),
      );
      await reload();
      if (kind === "publish") {
        setId("");
        setState(null);
        setDestination("");
        onPublished(result.dossier_id);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(null);
    }
  }
  function download(format: "json" | "md") {
    if (!state) return;
    const text =
      format === "json"
        ? JSON.stringify(state, null, 2)
        : state.pages
            .map(
              (p) =>
                `# Page ${p.page}\n\n${p.transcription}\n\n## ${t("Observations")}\n\n${p.observations}`,
            )
            .join("\n\n");
    const url = URL.createObjectURL(
      new Blob([text], { type: "text/plain;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `transcription.${format}`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const complete =
    !!state?.pages.length && state.pages.length === state.page_count;
  const running = doc?.status === "running";
  const queued = doc?.status === "queued";
  const failed = doc?.status === "error";
  const published = doc?.status === "done" && !dirty;
  const reading = running && doc.job?.stage.startsWith("OCR :");
  const stagePage = /OCR : (\d+)\/(\d+)/.exec(doc?.job?.stage || "");
  const total = state?.page_count || Number(stagePage?.[2]) || 0;
  const completed = state?.pages.length || 0;
  const step = !doc ? 0 : working || !complete ? 1 : 2;
  const pageData = state?.pages[page];
  const statusTitle = queued
    ? t("En attente de traitement")
    : reading
      ? t("Transcription en cours")
      : running
        ? t("Préparation pour la recherche")
        : failed
          ? t("Le traitement s’est interrompu")
          : published
            ? t("Disponible dans la recherche")
            : t("Transcription à vérifier");
  const statusDescription = queued
    ? t(
        "Votre document est dans la file. Le traitement démarrera dès que le serveur sera disponible.",
      )
    : reading
      ? t(
          "Inkling lit les pages une à une. Vous pouvez déjà consulter les pages terminées.",
        )
      : running
        ? t(
            "Le texte est en cours de préparation pour permettre la recherche dans ce dossier.",
          )
        : failed
          ? t(
              "Les pages terminées sont conservées. Vous pouvez reprendre le traitement sans renvoyer le PDF.",
            )
          : published
            ? t(
                "Vous pouvez maintenant retrouver les passages de ce document dans l’onglet Rechercher.",
              )
            : t(
                "Comparez le texte avec le PDF, corrigez si nécessaire, puis ajoutez le document à la recherche.",
              );

  return (
    <section
      className="ocr-panel"
      aria-label={t("Transcription des documents")}
    >
      <header className="ocr-intro">
        {uploadAllowed && (
          <p>
            {t(
              "Aucun dossier n’est choisi automatiquement. Sélectionnez une destination après vérification.",
            )}
          </p>
        )}
        <h2>{t("Du PDF au texte recherchable")}</h2>
        <p>
          {t(
            "Transcrivez un document scanné, vérifiez le texte, puis retrouvez-le dans vos recherches.",
          )}
        </p>
      </header>
      <ol className="ocr-steps" aria-label={t("Étapes du traitement")}>
        {[t("Choisir un PDF"), t("Transcrire"), t("Vérifier et ajouter")].map(
          (label, index) => (
            <li
              key={index}
              className={
                index === step ? "current" : index < step ? "complete" : ""
              }
              aria-current={index === step ? "step" : undefined}
            >
              <span>
                {index < step ? <CheckCircle2 size={17} /> : index + 1}
              </span>
              {label}
            </li>
          ),
        )}
      </ol>
      {uploadAllowed && (
        <section
          className="ocr-card ocr-import"
          aria-labelledby={`${prefix}-import`}
        >
          <h3 id={`${prefix}-import`}>
            <FileUp size={19} />
            {t("Nouveau document")}
          </h3>
          <div className="ocr-file-picker">
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,application/pdf"
              hidden
              onChange={(e) => {
                const candidate = e.target.files?.[0];
                setError("");
                if (
                  candidate &&
                  !candidate.name.toLowerCase().endsWith(".pdf")
                ) {
                  setError(t("Choisissez un fichier PDF."));
                  setFile(null);
                  return;
                }
                setFile(candidate || null);
              }}
            />
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              <FileUp size={17} />
              {t("Choisir un PDF")}
            </Button>
            <span className="ocr-file-name" dir="auto">
              {file
                ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} Mo`
                : t("Aucun fichier sélectionné")}
            </span>
            <Button disabled={!file || busy} onClick={() => void upload()}>
              {pending === "upload" ? (
                <LoaderCircle size={17} className="spin" />
              ) : (
                <ScanText size={17} />
              )}
              {t(
                pending === "upload"
                  ? "Envoi du document…"
                  : "Lancer la transcription",
              )}
            </Button>
          </div>
          <p className="ocr-hint">
            {t(
              "Le document sera transmis à Inkling sur le serveur de Stéphane.",
            )}
          </p>
        </section>
      )}
      {ocrDocuments.length > 0 && (
        <div className="ocr-document-picker">
          <label htmlFor={`${prefix}-document`}>
            {t("Suivre ou vérifier un document")}
          </label>
          <select
            id={`${prefix}-document`}
            value={id}
            disabled={busy}
            onChange={(e) => select(e.target.value)}
          >
            <option value="">{t("Choisissez un document")}</option>
            {ocrDocuments.map((d) => (
              <option key={d.document_id} value={d.document_id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
      )}
      {error && (
        <div role="alert" className="ocr-message ocr-message-error">
          <AlertCircle size={20} />
          <p>{error}</p>
        </div>
      )}
      {notice && (
        <div role="status" className="ocr-message">
          <CheckCircle2 size={19} />
          <p>{notice}</p>
        </div>
      )}
      {doc && (
        <section
          className={`ocr-card ocr-status ${failed ? "is-error" : published ? "is-done" : ""}`}
          aria-labelledby={`${prefix}-status`}
        >
          <div className="ocr-status-heading">
            {running || queued ? (
              <LoaderCircle size={23} className="spin" />
            ) : failed ? (
              <AlertCircle size={23} />
            ) : (
              <CheckCircle2 size={23} />
            )}
            <div>
              <h3 id={`${prefix}-status`} role="status">
                {statusTitle}
              </h3>
              <p>{statusDescription}</p>
            </div>
          </div>
          {total > 0 && !published && (
            <div className="ocr-progress">
              <div>
                <strong>
                  {completed} / {total} {t("pages transcrites")}
                </strong>
                {reading && stagePage && (
                  <span>
                    {t("Lecture de la page")} {stagePage[1]}
                  </span>
                )}
              </div>
              <progress
                value={completed}
                max={total}
                aria-label={t("Pages transcrites")}
              />
            </div>
          )}
          {failed && (
            <>
              <p className="ocr-hint">
                {t(
                  doc.job?.error ||
                    "Vérifiez le tunnel vers le serveur puis réessayez.",
                )}
              </p>
              <Button disabled={busy} onClick={() => void action("retry")}>
                <RotateCcw size={17} />
                {t("Reprendre la transcription")}
              </Button>
            </>
          )}
        </section>
      )}
      {loading && !state && (
        <p role="status" className="ocr-loading">
          <LoaderCircle className="spin" size={18} />
          {t("Chargement de la transcription…")}
        </p>
      )}
      {pageData && (
        <section
          className="ocr-card ocr-editor"
          aria-labelledby={`${prefix}-editor`}
        >
          <div className="ocr-editor-heading">
            <h3 id={`${prefix}-editor`}>{t("Vérifier la transcription")}</h3>
            <span className={`ocr-save-state ${dirty ? "unsaved" : ""}`}>
              {t(
                dirty
                  ? "Corrections non enregistrées"
                  : working
                    ? "Lecture seule pendant le traitement"
                    : "Modifications enregistrées",
              )}
            </span>
          </div>
          <div className="ocr-page-toolbar">
            <div className="ocr-page-navigation">
              <Button
                variant="outline"
                disabled={page === 0}
                onClick={() => show(page - 1)}
                aria-label={t("Page précédente")}
              >
                <ArrowLeft size={17} />
              </Button>
              <label htmlFor={`${prefix}-page`}>{t("Page")}</label>
              <select
                id={`${prefix}-page`}
                value={page}
                onChange={(e) => show(Number(e.target.value))}
              >
                {state?.pages.map((p, index) => (
                  <option value={index} key={p.page}>
                    {p.page}
                  </option>
                ))}
              </select>
              <span>/ {total}</span>
              <Button
                variant="outline"
                disabled={page + 1 >= completed}
                onClick={() => show(page + 1)}
                aria-label={t("Page suivante")}
              >
                <ArrowRight size={17} />
              </Button>
            </div>
            <Button variant="outline" onClick={() => show(page)}>
              <FileText size={17} />
              {t("Voir le PDF original")}
            </Button>
          </div>
          <label className="ocr-text-label" htmlFor={`${prefix}-text`}>
            {t("Texte de la page")}
          </label>
          <textarea
            id={`${prefix}-text`}
            dir="auto"
            rows={13}
            value={pageData.transcription}
            readOnly={working}
            aria-describedby={`${prefix}-help`}
            onChange={(e) => {
              const value = e.target.value;
              setState(
                (old) =>
                  old && {
                    ...old,
                    pages: old.pages.map((p, i) =>
                      i === page ? { ...p, transcription: value } : p,
                    ),
                  },
              );
              setDirty(true);
              setNotice("");
            }}
          />
          <p id={`${prefix}-help`} className="ocr-hint">
            {t(
              "Conservez les mentions d’incertitude et vérifiez les noms, dates et nombres dans le PDF.",
            )}
          </p>
          {pageData.observations && (
            <details className="ocr-observations">
              <summary>{t("Observations de cette page")}</summary>
              <p className="ocr-hint">
                {t("Ces observations ne sont pas ajoutées à la recherche.")}
              </p>
              <p dir="auto">{pageData.observations}</p>
            </details>
          )}
          <div className="ocr-editor-footer">
            <Button
              variant="outline"
              disabled={working || !dirty}
              onClick={() => void action("save")}
            >
              {pending === "save" ? (
                <LoaderCircle size={17} className="spin" />
              ) : (
                <Save size={17} />
              )}
              {t(
                pending === "save"
                  ? "Enregistrement…"
                  : "Enregistrer les corrections",
              )}
            </Button>
            {complete && !published && (
              <>
                <label>
                  {t("Dossier de destination")}
                  <select
                    value={destination}
                    onChange={(e) => setDestination(e.target.value)}
                    disabled={working}
                  >
                    <option value="">{t("Choisir un dossier")}</option>
                    {dossiers
                      .filter((d) => !d.archived)
                      .map((d) => (
                        <option key={d.dossier_id} value={d.dossier_id}>
                          {d.title}
                        </option>
                      ))}
                  </select>
                </label>
                <Button
                  disabled={working || !destination}
                  onClick={() => void action("publish")}
                >
                  {pending === "publish" ? (
                    <LoaderCircle size={17} className="spin" />
                  ) : (
                    <Search size={17} />
                  )}
                  {t("Ajouter à la recherche")}
                </Button>
              </>
            )}
          </div>
          <details className="ocr-secondary">
            <summary>{t("Téléchargement et nouvelle lecture")}</summary>
            <div className="ocr-secondary-group">
              <p>{t("Télécharger la transcription")}</p>
              <div className="ocr-actions">
                <Button variant="outline" onClick={() => download("md")}>
                  <Download size={16} />
                  {t("Texte Markdown")}
                </Button>
                <Button variant="outline" onClick={() => download("json")}>
                  <Download size={16} />
                  {t("Données JSON")}
                </Button>
              </div>
            </div>
            {!published && (
              <div className="ocr-secondary-group">
                <p>
                  {t(
                    "En cas de mauvaise lecture, demandez à Inkling de relire cette page. Les corrections non enregistrées seront perdues.",
                  )}
                </p>
                <Button
                  variant="outline"
                  disabled={working}
                  onClick={() => void action("retry", page + 1)}
                >
                  <RotateCcw size={16} />
                  {t("Relire cette page")}
                </Button>
              </div>
            )}
          </details>
        </section>
      )}
      {!doc && !loading && (
        <div className="ocr-empty">
          <ScanText size={30} />
          <p>{t("Choisissez un PDF ci-dessus pour commencer.")}</p>
          <span>
            {t(
              "Votre document sera ajouté à la recherche uniquement après votre vérification.",
            )}
          </span>
        </div>
      )}
    </section>
  );
}
