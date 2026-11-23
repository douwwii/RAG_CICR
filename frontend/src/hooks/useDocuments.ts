import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { SourceDocument } from "../types";
export function useDocuments(dossier: string) {
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);
  const reload = useCallback(async () => {
    const current = generation.current;
    if (!dossier) return;
    try {
      const docs = await api.documents(dossier);
      if (current === generation.current) {
        setDocuments(docs);
        setError("");
      }
    } catch (e) {
      if (current === generation.current) setError((e as Error).message);
    }
  }, [dossier]);
  useEffect(() => {
    generation.current++;
    setDocuments([]);
    setError("");
    setLoading(true);
    const current = generation.current;
    void reload().finally(() => {
      if (current === generation.current) setLoading(false);
    });
    const timer = setInterval(() => {
      void reload();
    }, 2500);
    return () => {
      generation.current++;
      clearInterval(timer);
    };
  }, [reload]);
  return { documents, error, loading, reload };
}
