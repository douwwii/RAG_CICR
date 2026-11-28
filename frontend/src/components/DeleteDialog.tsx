import { useEffect, useRef, useState } from "react";
import { useLanguage } from "../i18n";
import { api } from "../api/client";
import { Button } from "./ui/button";
export interface DeleteTarget {
  dossier: string;
  document?: string;
  name: string;
}
export function DeleteDialog({
  target,
  onClose,
  onDone,
}: {
  target: DeleteTarget;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const { t } = useLanguage();
  const ref = useRef<HTMLDialogElement>(null);
  const [processing, setProcessing] = useState<boolean | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    ref.current?.showModal();
    let live = true;
    async function check() {
      try {
        const docs = await api.documents(target.dossier);
        if (live)
          setProcessing(
            docs.some(
              (d) =>
                (!target.document || d.document_id === target.document) &&
                ["queued", "running"].includes(d.status),
            ),
          );
      } catch (e) {
        if (live) {
          setProcessing(null);
          setError((e as Error).message);
        }
      }
    }
    void check();
    const timer = setInterval(() => {
      void check();
    }, 2500);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [target.dossier, target.document]);
  async function remove() {
    if (!confirmed || busy || processing !== false) return;
    setBusy(true);
    try {
      await api.deleteItem(target.dossier, target.document);
      await onDone();
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={ref}
      className="manage-dialog"
      aria-labelledby="delete-heading"
      onCancel={(e) => {
        if (busy) e.preventDefault();
        else onClose();
      }}
    >
      <h2 id="delete-heading">
        {t(target.document ? "Supprimer le document" : "Supprimer le dossier")}
      </h2>
      <p dir="auto">
        <strong>{target.name}</strong>
      </p>
      <p className="delete-warning">
        {t(
          target.document
            ? "Ce document et ses passages seront supprimés de l’application. Cette action est irréversible."
            : "Ce dossier et tous ses documents seront supprimés de l’application. Cette action est irréversible.",
        )}
      </p>
      {processing !== false && (
        <p role="status" className="archive-confirm">
          {t(
            processing
              ? "Un traitement de document est en cours. Attendez sa fin avant de supprimer."
              : "Vérification des traitements en cours…",
          )}
        </p>
      )}
      <label className="delete-check">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={busy || processing !== false}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        {t("Je confirme cette suppression.")}
      </label>
      {error && (
        <p className="error-message" role="alert">
          {t(error)}
        </p>
      )}
      <div className="dialog-actions">
        <Button autoFocus variant="outline" disabled={busy} onClick={onClose}>
          {t("Annuler")}
        </Button>
        <Button
          className="button-danger"
          disabled={!confirmed || busy || processing !== false}
          onClick={() => {
            void remove();
          }}
        >
          {t(busy ? "En cours" : "Supprimer définitivement")}
        </Button>
      </div>
    </dialog>
  );
}
