import { useEffect, useRef, useState } from "react";
import { useLanguage } from "../i18n";
import { api } from "../api/client";
import type { Dossier, SourceDocument } from "../types";
import { Button } from "./ui/button";
export type ManagementAction =
  | { kind: "create" }
  | { kind: "dossier"; dossier: Dossier }
  | { kind: "move"; document: SourceDocument };
export function ManageDialog({
  action,
  dossier,
  dossiers,
  onClose,
  onDelete,
  onDone,
}: {
  action: ManagementAction;
  dossier: string;
  dossiers: Dossier[];
  onClose: () => void;
  onDelete: () => void;
  onDone: (id?: string) => Promise<void>;
}) {
  const { t } = useLanguage();
  const ref = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState(
    action.kind === "dossier" ? action.dossier.title : "",
  );
  const [destination, setDestination] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmArchive, setConfirmArchive] = useState(false);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  async function save(archive = false) {
    setBusy(true);
    setError("");
    try {
      let selected: string | undefined;
      if (action.kind === "create")
        selected = (await api.createDossier(name.trim())).dossier_id;
      if (action.kind === "dossier")
        await api.updateDossier(
          action.dossier.dossier_id,
          archive
            ? { archived: !action.dossier.archived }
            : { title: name.trim() },
        );
      if (action.kind === "move")
        await api.moveDocument(
          dossier,
          action.document.document_id,
          destination,
        );
      await onDone(selected);
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
      aria-labelledby="manage-heading"
      onCancel={(e) => {
        if (busy) e.preventDefault();
        else onClose();
      }}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <h2 id="manage-heading">
          {t(
            action.kind === "create"
              ? "Nouveau dossier"
              : action.kind === "move"
                ? "Déplacer le document"
                : "Gérer le dossier",
          )}
        </h2>
        {action.kind === "move" ? (
          <>
            <p dir="auto">{action.document.name}</p>
            <label>
              {t("Dossier de destination")}
              <select
                autoFocus
                required
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
              >
                <option value="">{t("Choisir un dossier")}</option>
                {dossiers
                  .filter((d) => !d.archived && d.dossier_id !== dossier)
                  .map((d) => (
                    <option key={d.dossier_id} value={d.dossier_id}>
                      {d.title}
                    </option>
                  ))}
              </select>
            </label>
            <p className="muted">
              {t(
                "Le document et ses résultats de recherche seront transférés dans ce dossier.",
              )}
            </p>
          </>
        ) : (
          <label>
            {t("Nom du dossier")}
            <input
              autoFocus
              required
              maxLength={160}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
        )}
        {error && (
          <p role="alert" className="error-message">
            {t(error)}
          </p>
        )}
        {confirmArchive && (
          <p className="archive-confirm" role="status">
            {t(
              "Archiver ce dossier ? Ses documents seront conservés. Vous pourrez le restaurer.",
            )}
          </p>
        )}
        <div className="dialog-actions">
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={onClose}
          >
            {t("Annuler")}
          </Button>
          <Button
            type="submit"
            disabled={
              busy || (action.kind === "move" ? !destination : !name.trim())
            }
          >
            {t(busy ? "En cours" : "Enregistrer")}
          </Button>
        </div>
        {action.kind === "dossier" && (
          <div className="archive-action">
            <Button
              type="button"
              variant="ghost"
              className="danger-text"
              disabled={busy}
              onClick={onDelete}
            >
              {t("Supprimer le dossier")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                if (action.dossier.archived || confirmArchive) void save(true);
                else setConfirmArchive(true);
              }}
            >
              {t(
                action.dossier.archived
                  ? "Restaurer le dossier"
                  : confirmArchive
                    ? "Confirmer l’archivage"
                    : "Archiver le dossier",
              )}
            </Button>
          </div>
        )}
      </form>
    </dialog>
  );
}
