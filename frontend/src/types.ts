export interface Dossier {
  archived?: boolean;
  dossier_id: string;
  title: string;
  person_ids: string[];
}
export type Status = "queued" | "running" | "done" | "error" | "not_indexed" | "review";
export interface Job {
  job_id: string;
  document_id: string;
  dossier_id: string;
  filename: string;
  status: Status;
  stage: string;
  error: string | null;
  warning: string | null;
  page_count: number | null;
  passage_count: number | null;
}
export interface SourceDocument {
  document_id: string;
  dossier_id: string;
  name: string;
  kind: string;
  status: Status;
  job: Job | null;
  has_pdf: boolean;
  ocr?: boolean;
}
export type SearchMode = "semantic" | "hybrid" | "exact";
export interface Hit {
  passage_id: string;
  document_id: string;
  dossier_id: string;
  title: string;
  text: string;
  score: number;
  score_kind?: "lexical" | "rrf";
  relevance?: "direct" | "partial" | "context" | "unrelated";
  relevance_reason?: string;
  evidence_quote?: string;
  page_start: number | null;
  page_end: number | null;
  name: string;
  kind: string;
}
export interface Selection {
  dossier_id?: string;
  document_id: string;
  name: string;
  page: number;
  text?: string;
}
export interface Source {
  kind: "pdf" | "text";
  name: string;
  text?: string;
}

export interface SearchResponse {
  retrieval: {mode: SearchMode; document_ids: string[] | null};
  results: Hit[];
  assessment: {
    coverage: "direct" | "partial" | "context" | "none" | "contradictory";
    summary: { text: string; passage_ids: string[] }[];
  } | null;
  reranking: {
    status: "applied" | "fallback" | "empty";
    candidate_count: number;
    calls: number;
    duration_seconds: number;
    warning: string | null;
  };
}

export interface OCRState {
  pages: {page: number; transcription: string; observations: string; raw: string}[];
  page_count?: number;
  model?: string;
}
