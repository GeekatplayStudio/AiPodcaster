import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { EditProposal } from "../api/types";
import { KIND_LABELS, formatTime } from "../lib/format";

export interface PlayerHandle {
  seek: (ms: number, play?: boolean) => void;
}

interface Props {
  src: string;
  durationMs: number;
  proposals: EditProposal[];
  onPick?: (proposal: EditProposal) => void;
}

/** Native audio element plus a timeline that shows every proposed cut. */
export const AudioPlayer = forwardRef<PlayerHandle, Props>(function AudioPlayer({ src, durationMs, proposals, onPick }, ref) {
  const { t } = useTranslation("job");
  const audioRef = useRef<HTMLAudioElement>(null);
  const [position, setPosition] = useState(0);
  const [previewStop, setPreviewStop] = useState<number | null>(null);

  useImperativeHandle(ref, () => ({
    seek: (ms, play) => {
      const audio = audioRef.current;
      if (!audio) return;
      audio.currentTime = Math.max(0, ms / 1000);
      if (play) void audio.play().catch(() => undefined);
    },
  }));

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onTime = () => {
      setPosition(audio.currentTime * 1000);
      if (previewStop !== null && audio.currentTime * 1000 >= previewStop) {
        audio.pause();
        setPreviewStop(null);
      }
    };
    audio.addEventListener("timeupdate", onTime);
    return () => audio.removeEventListener("timeupdate", onTime);
  }, [previewStop]);

  function preview(proposal: EditProposal) {
    const audio = audioRef.current;
    if (!audio) return;
    const start = Math.max(0, proposal.start_ms - 1200);
    setPreviewStop(Math.min(durationMs, proposal.end_ms + 1200));
    audio.currentTime = start / 1000;
    void audio.play().catch(() => undefined);
    onPick?.(proposal);
  }

  const total = Math.max(durationMs, 1);
  return (
    <div className="player">
      <audio ref={audioRef} controls preload="metadata" src={src} aria-label={t("Original recording")} />
      <div className="timeline" aria-label={t("Proposed cuts on the timeline")}>
        {proposals.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`cut${p.accepted ? "" : " rejected"}`}
            style={{ left: `${(p.start_ms / total) * 100}%`, width: `${Math.max(((p.end_ms - p.start_ms) / total) * 100, 0.25)}%`, background: `var(--${p.kind})`, border: "none", padding: 0 }}
            title={`${t(KIND_LABELS[p.kind])} · ${formatTime(p.start_ms)} · ${p.reason}`}
            aria-label={t("Preview {{kind}} at {{time}}", { kind: t(KIND_LABELS[p.kind]), time: formatTime(p.start_ms) })}
            onClick={() => preview(p)}
          />
        ))}
        <span className="playhead" style={{ left: `${Math.min(100, (position / total) * 100)}%` }} />
      </div>
      <div className="legend" aria-hidden="true">
        <span>
          <i style={{ background: "var(--profanity)" }} /> {t("Profanity")}
        </span>
        <span>
          <i style={{ background: "var(--filler)" }} /> {t("Filler")}
        </span>
        <span>
          <i style={{ background: "var(--repeat)" }} /> {t("Repeat")}
        </span>
        <span>
          <i style={{ background: "var(--silence)" }} /> {t("Pause")}
        </span>
        <span className="muted">{t("Click a marker to hear it in context.")}</span>
      </div>
    </div>
  );
});
