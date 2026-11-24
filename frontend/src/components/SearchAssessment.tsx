import type { Hit, SearchResponse } from "../types";
import { Button } from "./ui/button";
export function SearchAssessment({
  analysis,
  onOpen,
}: {
  analysis: SearchResponse;
  onOpen: (hit: Hit) => void;
}) {
  const labels = {
    direct: "Des éléments répondent directement",
    partial: "Réponse partielle",
    context: "Contexte disponible",
    none: "Réponse non établie par ces extraits",
    contradictory: "Sources contradictoires",
  };
  return (
    <>
      {analysis.reranking.warning && (
        <div role="status" className="error-message">
          {analysis.reranking.warning}
        </div>
      )}
      {analysis.assessment && (
        <div className="assessment" aria-label="Bilan de pertinence">
          <span className="eyebrow">
            LIEN AVEC VOTRE QUESTION
          </span>
          <h3>{labels[analysis.assessment.coverage]}</h3>
          {analysis.assessment.summary.map((sentence, index) => (
            <p key={index}>
              {sentence.text}{" "}
              {sentence.passage_ids.map((id) => {
                const rank = analysis.results.findIndex(
                  (hit) => hit.passage_id === id,
                );
                return rank >= 0 ? (
                  <Button
                    key={id}
                    variant="ghost"
                    className="citation"
                    onClick={() => onOpen(analysis.results[rank])}
                    aria-label={`Consulter le passage ${rank + 1}`}
                  >
                    [{rank + 1}]
                  </Button>
                ) : null;
              })}
            </p>
          ))}
          <small>
            Analyse produite par Qwen sur {analysis.reranking.candidate_count}{" "}
            candidats du dossier. Vérifiez les sources ; ce bilan n’établit pas
            la vérité des faits.
          </small>
        </div>
      )}
    </>
  );
}
