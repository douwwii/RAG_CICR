import { useLanguage } from "../i18n";
import type { Hit, SearchResponse } from "../types";
import { Button } from "./ui/button";
export function SearchAssessment({
  analysis,
  onOpen,
}: {
  analysis: SearchResponse;
  onOpen: (hit: Hit) => void;
}) {
  const { t } = useLanguage();
  const labels = {
    direct: t("Des éléments répondent directement"),
    partial: t("Réponse partielle"),
    context: t("Contexte disponible"),
    none: t("Réponse non établie par ces extraits"),
    contradictory: t("Sources contradictoires"),
  };
  return (
    <>
      {analysis.reranking.warning && (
        <div role="status" className="error-message">
          {t(analysis.reranking.warning)}
        </div>
      )}
      {analysis.assessment && (
        <div className="assessment" aria-label={t("Bilan de pertinence")}>
          <span className="eyebrow">{t("LIEN AVEC VOTRE QUESTION")}</span>
          <h3>{labels[analysis.assessment.coverage]}</h3>
          {analysis.assessment.summary.slice(0,1).map((sentence, index) => (
            <p key={index}>
              {t(sentence.text)}{" "}
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
                    aria-label={`${t("Consulter le passage")} ${rank + 1}`}
                  >
                    [{rank + 1}]
                  </Button>
                ) : null;
              })}
            </p>
          ))}
          <small>
            {t("Analyse produite par Qwen sur")}{" "}
            {analysis.reranking.candidate_count}{" "}
            {t(
              "candidats du dossier. Vérifiez les sources ; ce bilan n’établit pas la vérité des faits.",
            )}
          </small>
        </div>
      )}
    </>
  );
}
