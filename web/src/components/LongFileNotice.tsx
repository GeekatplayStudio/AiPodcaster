import { useTranslation } from "react-i18next";
import type { ApiInfo } from "../api/types";
import { friendlyDuration, processingRange } from "../lib/estimate";
import { formatBytes, formatTime } from "../lib/format";

interface Props {
  fileName: string;
  sizeBytes: number;
  durationSeconds: number;
  info: ApiInfo | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Shown before uploading a long recording: what to expect and that it is safe to leave. */
export function LongFileNotice({ fileName, sizeBytes, durationSeconds, info, onConfirm, onCancel }: Props) {
  const { t } = useTranslation("library");
  const [low, high] = processingRange(durationSeconds, info);
  const device = info?.estimates.device === "gpu" ? t("on your GPU") : t("on the CPU");
  return (
    <div className="alert warn long-file" role="alertdialog" aria-labelledby="long-file-title">
      <strong id="long-file-title">{t("This is a long recording")}</strong>
      <p style={{ margin: "0.35rem 0" }}>
        {fileName} · {durationSeconds ? formatTime(durationSeconds * 1000) : t("length unknown")} · {formatBytes(sizeBytes)}
      </p>
      <p style={{ margin: "0.35rem 0" }}>
        {durationSeconds
          ? t("Expect roughly {{low}} to {{high}} of processing {{device}} before the review is ready, plus upload time.", { low: friendlyDuration(low), high: friendlyDuration(high), device })
          : t("Large files take a while to upload and transcribe.")}{" "}
        {t("You can close this tab once the upload finishes; processing continues on the server and resumes after a restart.")}
      </p>
      <p className="small" style={{ margin: "0.35rem 0" }}>
        {t("Tip: for multi-gigabyte videos, “Link or large file” imports straight from disk without uploading.")}
      </p>
      <div className="btn-row">
        <button type="button" className="btn primary" onClick={onConfirm}>
          {t("Upload and process")}
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          {t("Cancel")}
        </button>
      </div>
    </div>
  );
}
