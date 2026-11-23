import type { Dossier, Hit, Job, Source, SourceDocument } from "../types";
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
  dossiers: () => request<Dossier[]>("/dossiers"),
  documents: (id: string) =>
    request<SourceDocument[]>(scope(id) + "/documents"),
  search: (id: string, question: string, signal: AbortSignal) =>
    request<{ results: Hit[] }>(scope(id) + "/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, top_k: 5 }),
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
