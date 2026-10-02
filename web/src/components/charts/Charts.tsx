import { useId, useState, type ReactNode } from "react";

/**
 * Small dependency-free SVG charts. Colors follow the dataviz reference palette:
 * categorical slots in fixed order, one sequential hue, status colors reserved.
 */
export const SERIES = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)"];

export interface Series {
  name: string;
  values: number[];
  color?: string;
}

interface TooltipState {
  x: number;
  y: number;
  content: ReactNode;
}

function Tooltip({ state }: { state: TooltipState | null }) {
  if (!state) return null;
  return (
    <div className="chart-tooltip" style={{ left: state.x, top: state.y }} role="status">
      {state.content}
    </div>
  );
}

export function StatTile({ label, value, hint, tone }: { label: string; value: string | number; hint?: string; tone?: "good" | "warning" | "serious" }) {
  return (
    <div className={`stat${tone ? ` tone-${tone}` : ""}`}>
      <strong>{value}</strong>
      <span>
        {label}
        {hint ? ` · ${hint}` : ""}
      </span>
    </div>
  );
}

export function BarChart({ labels, series, height = 200, stacked = false, formatValue = (v: number) => String(v), horizontal = false }: { labels: string[]; series: Series[]; height?: number; stacked?: boolean; formatValue?: (value: number) => string; horizontal?: boolean }) {
  const [tip, setTip] = useState<TooltipState | null>(null);
  const id = useId();
  const width = 600;
  const pad = { top: 12, right: 12, bottom: horizontal ? 24 : 36, left: horizontal ? 110 : 40 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const totals = labels.map((_, i) => (stacked ? series.reduce((sum, s) => sum + (s.values[i] ?? 0), 0) : Math.max(...series.map((s) => s.values[i] ?? 0))));
  const max = Math.max(1, ...totals);
  const n = labels.length || 1;
  const groupSize = (horizontal ? innerH : innerW) / n;
  const barThickness = Math.max(4, Math.min(28, (groupSize * 0.7) / (stacked ? 1 : series.length)));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(max * f));

  return (
    <div className="chart" onMouseLeave={() => setTip(null)}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby={`${id}-title`} preserveAspectRatio="xMidYMid meet">
        <title id={`${id}-title`}>{series.map((s) => s.name).join(", ")}</title>
        {ticks.map((t) => {
          const pos = horizontal ? pad.left + (t / max) * innerW : pad.top + innerH - (t / max) * innerH;
          return horizontal ? (
            <g key={t}>
              <line x1={pos} x2={pos} y1={pad.top} y2={pad.top + innerH} className="grid" />
              <text x={pos} y={height - 8} className="axis" textAnchor="middle">
                {formatValue(t)}
              </text>
            </g>
          ) : (
            <g key={t}>
              <line x1={pad.left} x2={width - pad.right} y1={pos} y2={pos} className="grid" />
              <text x={pad.left - 6} y={pos + 4} className="axis" textAnchor="end">
                {formatValue(t)}
              </text>
            </g>
          );
        })}
        {labels.map((label, i) => {
          const lengths = series.map((s) => ((s.values[i] ?? 0) / max) * (horizontal ? innerW : innerH));
          const starts = lengths.map((_, si) => (stacked ? lengths.slice(0, si).reduce((sum, l) => sum + l, 0) : 0));
          return (
            <g key={label + i}>
              {series.map((s, si) => {
                const value = s.values[i] ?? 0;
                const length = lengths[si];
                const color = s.color ?? SERIES[si % SERIES.length];
                const base = (horizontal ? pad.top : pad.left) + i * groupSize + (groupSize - (stacked ? barThickness : barThickness * series.length)) / 2 + (stacked ? 0 : si * barThickness);
                const start = starts[si];
                const rectProps = horizontal
                  ? { x: pad.left + start, y: base, width: Math.max(length - (stacked && si > 0 ? 2 : 0), 0), height: barThickness }
                  : { x: base, y: pad.top + innerH - start - length, width: barThickness, height: Math.max(length - (stacked && si > 0 ? 2 : 0), 0) };
                return (
                  <rect
                    key={s.name}
                    {...rectProps}
                    rx={3}
                    fill={color}
                    className="bar"
                    onMouseMove={(e) => setTip({ x: e.nativeEvent.offsetX + 12, y: e.nativeEvent.offsetY - 10, content: `${label} · ${s.name}: ${formatValue(value)}` })}
                  />
                );
              })}
              {horizontal ? (
                <text x={pad.left - 8} y={pad.top + i * groupSize + groupSize / 2 + 4} className="axis" textAnchor="end">
                  {label.length > 16 ? `${label.slice(0, 15)}…` : label}
                </text>
              ) : (
                (n <= 16 || i % Math.ceil(n / 16) === 0) && (
                  <text x={pad.left + i * groupSize + groupSize / 2} y={height - 10} className="axis" textAnchor="middle">
                    {label}
                  </text>
                )
              )}
            </g>
          );
        })}
      </svg>
      {series.length > 1 && <Legend series={series} />}
      <Tooltip state={tip} />
    </div>
  );
}

export function LineChart({ labels, series, height = 200, formatValue = (v: number) => String(v) }: { labels: string[]; series: Series[]; height?: number; formatValue?: (value: number) => string }) {
  const [tip, setTip] = useState<TooltipState | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const id = useId();
  const width = 600;
  const pad = { top: 12, right: 12, bottom: 32, left: 40 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  const n = Math.max(labels.length, 1);
  const x = (i: number) => pad.left + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => pad.top + innerH - (v / max) * innerH;
  const ticks = [0, 0.5, 1].map((f) => Math.round(max * f));

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * width;
    const index = Math.max(0, Math.min(n - 1, Math.round(((px - pad.left) / innerW) * (n - 1))));
    setHover(index);
    setTip({ x: e.nativeEvent.offsetX + 12, y: e.nativeEvent.offsetY - 10, content: `${labels[index]} · ${series.map((s) => `${s.name}: ${formatValue(s.values[index] ?? 0)}`).join(" · ")}` });
  }

  return (
    <div className="chart" onMouseLeave={() => (setTip(null), setHover(null))}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby={`${id}-title`} onMouseMove={onMove} preserveAspectRatio="xMidYMid meet">
        <title id={`${id}-title`}>{series.map((s) => s.name).join(", ")}</title>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} className="grid" />
            <text x={pad.left - 6} y={y(t) + 4} className="axis" textAnchor="end">
              {formatValue(t)}
            </text>
          </g>
        ))}
        {labels.map((label, i) => (n <= 12 || i % Math.ceil(n / 12) === 0) && (
          <text key={label + i} x={x(i)} y={height - 8} className="axis" textAnchor="middle">
            {label}
          </text>
        ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + innerH} className="crosshair" />}
        {series.map((s, si) => {
          const color = s.color ?? SERIES[si % SERIES.length];
          const path = s.values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(v)}`).join(" ");
          return (
            <g key={s.name}>
              <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
              {hover !== null && <circle cx={x(hover)} cy={y(s.values[hover] ?? 0)} r={5} fill={color} stroke="var(--surface)" strokeWidth={2} />}
            </g>
          );
        })}
      </svg>
      {series.length > 1 && <Legend series={series} />}
      <Tooltip state={tip} />
    </div>
  );
}

export function Donut({ items, size = 160, formatValue = (v: number) => String(v) }: { items: { label: string; value: number; color?: string }[]; size?: number; formatValue?: (value: number) => string }) {
  const [tip, setTip] = useState<TooltipState | null>(null);
  const total = items.reduce((sum, item) => sum + item.value, 0);
  const radius = size / 2 - 6;
  const circumference = 2 * Math.PI * radius;
  const offsets: number[] = [];
  items.reduce((acc, item) => {
    offsets.push(acc);
    return acc + (total ? item.value / total : 0) * circumference;
  }, 0);
  return (
    <div className="chart donut" onMouseLeave={() => setTip(null)}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} role="img" aria-label={items.map((i) => `${i.label} ${i.value}`).join(", ")}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--surface-2)" strokeWidth={14} />
        {items.map((item, i) => {
          const fraction = total ? item.value / total : 0;
          const dash = Math.max(fraction * circumference - 2, 0);
          return (
            <circle
              key={item.label}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={item.color ?? SERIES[i % SERIES.length]}
              strokeWidth={14}
              strokeDasharray={`${dash} ${circumference - dash}`}
              strokeDashoffset={-offsets[i]}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
              onMouseMove={(e) => setTip({ x: e.nativeEvent.offsetX + 12, y: e.nativeEvent.offsetY - 10, content: `${item.label}: ${formatValue(item.value)} (${Math.round(fraction * 100)}%)` })}
            />
          );
        })}
        <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" className="donut-total">
          {formatValue(total)}
        </text>
      </svg>
      <Legend series={items.map((item, i) => ({ name: `${item.label} (${item.value})`, values: [], color: item.color ?? SERIES[i % SERIES.length] }))} />
      <Tooltip state={tip} />
    </div>
  );
}

function Legend({ series }: { series: Series[] }) {
  return (
    <ul className="legend chart-legend">
      {series.map((s, i) => (
        <li key={s.name}>
          <i style={{ background: s.color ?? SERIES[i % SERIES.length] }} /> {s.name}
        </li>
      ))}
    </ul>
  );
}
