interface BarDatum {
  label: string;
  value: number;
}

interface Props {
  data: BarDatum[];
  height?: number;
}

const COLORS = [
  "#2563eb", "#16a34a", "#d97706", "#dc2626",
  "#7c3aed", "#0891b2", "#be185d", "#65a30d",
];

export default function BarChart({ data, height = 180 }: Props) {
  if (!data || data.length === 0) {
    return <p className="empty-state">No chart data available.</p>;
  }

  const max = Math.max(...data.map((d) => d.value), 1);
  const barWidth = Math.max(24, Math.floor(460 / data.length) - 8);
  const svgWidth = data.length * (barWidth + 8) + 40;

  return (
    <div className="chart-wrap" style={{ overflowX: "auto" }}>
      <svg
        width={svgWidth}
        height={height + 40}
        aria-label="Spending by category bar chart"
      >
        {data.map((d, i) => {
          const barH = Math.max(4, Math.round((d.value / max) * height));
          const x = 20 + i * (barWidth + 8);
          const y = height - barH + 4;
          const color = COLORS[i % COLORS.length];

          return (
            <g key={d.label}>
              <title>{`${d.label}: $${d.value.toFixed(2)}`}</title>
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={barH}
                fill={color}
                rx={3}
              />
              <text
                x={x + barWidth / 2}
                y={height + 18}
                textAnchor="middle"
                fontSize={10}
                fill="#555"
              >
                {d.label.length > 8 ? d.label.slice(0, 7) + "…" : d.label}
              </text>
              <text
                x={x + barWidth / 2}
                y={y - 4}
                textAnchor="middle"
                fontSize={9}
                fill="#333"
              >
                ${d.value >= 1000 ? (d.value / 1000).toFixed(1) + "k" : d.value.toFixed(0)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
