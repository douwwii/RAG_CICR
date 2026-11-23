import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FileUp,
  LoaderCircle,
  Upload,
  X,
} from "lucide-react";
import { api } from "../api/client";
import { Button } from "./ui/button";
export function ImportDialog({
  dossier,
  title,
  onClose,
  onImported,
}: {
  dossier: string;
  title: string;
  onClose: () => void;
  onImported: () => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  function select(candidate?: File) {
    setError("");
    setMessage("");
    setFile(null);
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith(".pdf")) {
      setError("Choisissez un fichier PDF.");
      return;
    }
    if (candidate.size > 20 * 1024 * 1024) {
      setError("Le fichier dépasse la limite de 20 Mo.");
      return;
    }
    setFile(candidate);
  }
  async function submit() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.upload(dossier, file);
      setMessage(
        result.duplicate
          ? "Ce document existe déjà dans ce dossier. Son statut figure dans la liste des documents."
          : "Document reçu. Vous pouvez suivre son traitement dans la liste des documents.",
      );
      setFile(null);
      await onImported();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="import-dialog"
      aria-labelledby="import-title"
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else onClose();
      }}
    >
      <div className="dialog-head">
        <span className="file-square">
          <FileUp size={22} />
        </span>
        <Button
          variant="ghost"
          size="icon"
          disabled={busy}
          onClick={onClose}
          aria-label="Fermer l’importation"
        >
          <X size={18} />
        </Button>
      </div>
      <h2 id="import-title">Ajouter une pièce au dossier</h2>
      <p className="muted">
        Le document sera extrait, découpé par Qwen puis indexé pour la
        recherche.
      </p>
      <div className="destination">
        <span className="eyebrow">DOSSIER DE DESTINATION</span>
        <strong>{title}</strong>
        <span>{dossier}</span>
      </div>
      <button
        disabled={busy}
        className={`dropzone ${dragging ? "dragging" : ""}`}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          select(e.dataTransfer.files[0]);
        }}
      >
        <Upload size={25} />
        <strong>{file ? file.name : "Déposez votre PDF ici"}</strong>
        <span>
          {file
            ? `${(file.size / 1024).toFixed(0)} Ko · Prêt à envoyer`
            : "ou cliquez pour choisir un fichier"}
        </span>
        <small>PDF avec texte numérique · 20 Mo maximum</small>
      </button>
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        hidden
        onChange={(e) => select(e.target.files?.[0])}
      />
      <p className="import-limit">
        V1 : jusqu’à 100 pages et 24 000 caractères extraits. Les pages sans
        texte exploitable sont refusées.
      </p>
      {error && (
        <div className="error-message" role="alert">
          <AlertCircle size={17} />
          {error}
        </div>
      )}
      {message && (
        <div className="success-message" role="status">
          <CheckCircle2 size={18} />
          {message}
        </div>
      )}
      <div className="dialog-actions">
        <Button variant="outline" onClick={onClose} disabled={busy}>
          {message ? "Fermer" : "Annuler"}
        </Button>
        <Button
          onClick={() => {
            void submit();
          }}
          disabled={!file || busy}
        >
          {busy ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <Upload size={16} />
          )}{" "}
          {busy ? "Envoi du document…" : "Importer et indexer"}
        </Button>
      </div>
    </dialog>
  );
}
