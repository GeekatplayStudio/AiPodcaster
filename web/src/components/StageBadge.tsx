import { useTranslation } from "react-i18next";
import type { JobStage } from "../api/types";
import { STAGE_LABELS, isProcessing } from "../lib/format";

export function StageBadge({ stage, progress }: { stage: JobStage; progress?: number }) {
  const { t } = useTranslation();
  const cls = stage === "complete" ? "ok" : stage === "failed" ? "fail" : stage === "waiting_for_approval" ? "review" : "busy";
  return (
    <span className={`badge ${cls}`}>
      {isProcessing(stage) && <span className="spinner" aria-hidden="true" style={{ width: 10, height: 10 }} />}
      {t(STAGE_LABELS[stage])}
      {isProcessing(stage) && progress !== undefined ? ` ${progress}%` : ""}
    </span>
  );
}

const STEP_LABELS = ["Upload", "Analyse", "Review & approve", "Produce", "Publish"];

export function Steps({ stage }: { stage: JobStage }) {
  const { t } = useTranslation();
  const current = stage === "failed" ? -1 : ["uploaded", "ingest", "transcribe", "propose_edits"].includes(stage) ? 1 : stage === "waiting_for_approval" ? 2 : stage === "render" ? 3 : 4;
  return (
    <ol className="steps" aria-label={t("Workflow")}>
      {STEP_LABELS.map((label, index) => (
        <li key={label} className={index < current ? "done" : index === current ? "current" : ""} aria-current={index === current ? "step" : undefined}>
          {t(label)}
        </li>
      ))}
    </ol>
  );
}
