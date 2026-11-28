import type {
  OCRState,
  SearchResponse,
  SearchMode,
  Dossier,
  Job,
  Source,
  SourceDocument,
} from "../types";
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch("/api" + path, init);
  } catch {
    throw new Error(
      "Le serveur local est inaccessible. Vérifiez que le backend est démarré.",
    );
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      typeof error?.detail === "string" ? error.detail : "La requête a échoué.",
    );
  }
  return response.json() as Promise<T>;
}
const scope = (id: string) => `/dossiers/${encodeURIComponent(id)}`;
export const api = {
  ocr: (id: string, document: string) =>
    request<OCRState>(
      scope(id) + `/documents/${encodeURIComponent(document)}/ocr`,
    ),
  editOCR: (
    id: string,
    document: string,
    data: {
      pages?: string[];
      publish?: boolean;
      retry?: boolean;
      retry_page?: number;
      destination?: string;
    },
  ) =>
    request<{ ok: boolean; dossier_id: string }>(
      scope(id) + `/documents/${encodeURIComponent(document)}/ocr`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      },
    ),
  uploadOCR: (id: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<{ job: Job }>(scope(id) + "/ocr-imports", {
      method: "POST",
      body,
    });
  },
  deleteItem: (id: string, document?: string) =>
    request(
      scope(id) +
        (document ? `/documents/${encodeURIComponent(document)}` : "") +
        "?confirmed=true",
      { method: "DELETE" },
    ),
  retryDocument: (id: string, document: string) =>
    request(scope(id) + `/documents/${encodeURIComponent(document)}/retry`, {
      method: "POST",
    }),
  createDossier: (title: string) =>
    request<Dossier>("/dossiers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  updateDossier: (id: string, data: { title?: string; archived?: boolean }) =>
    request(scope(id), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  moveDocument: (id: string, document: string, destination: string) =>
    request(scope(id) + `/documents/${encodeURIComponent(document)}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ destination }),
    }),
  dossiers: () => request<Dossier[]>("/dossiers"),
  documents: (id: string) =>
    request<SourceDocument[]>(scope(id) + "/documents"),
  search: (id: string, question: string, signal: AbortSignal, mode: SearchMode, document_ids: string[] | null) =>
    request<SearchResponse>(scope(id) + "/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, top_k: 5, mode, document_ids }),
      signal,
    }),
  upload: (id: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<{ job: Job; duplicate: boolean }>(scope(id) + "/imports", {
      method: "POST",
      body,
    });
  },
  source: (id: string, document: string, signal: AbortSignal) =>
    request<Source>(
      scope(id) + `/documents/${encodeURIComponent(document)}/source`,
      { signal },
    ),
  file: (id: string, document: string) =>
    "/api" + scope(id) + `/documents/${encodeURIComponent(document)}/file`,
};
