import { createChart } from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import { useTheme } from "../theme.jsx";

// lightweight-charts prints unix times as UTC. Shift intraday bars by +5:30
// so the axis reads India time for everyone, not the viewer's zone.
const IST_SHIFT_SECONDS = 5.5 * 60 * 60;

function prepare(bars, intraday) {
  const seen = new Set();
  const points = [];
  for (const bar of bars || []) {
    const open = Number(bar.open);
    const high = Number(bar.high);
    const low = Number(bar.low);
    const close = Number(bar.close);
    if (![open, high, low, close].every(Number.isFinite)) continue;
    const time = intraday ? Number(bar.time) + IST_SHIFT_SECONDS : bar.time;
    if (seen.has(time)) continue;
    seen.add(time);
    points.push({ time, open, high, low, close });
  }
  points.sort((a, b) => (a.time > b.time ? 1 : a.time < b.time ? -1 : 0));
  return points;
}

function cssColor(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export default function PriceChart({ bars, intraday }) {
  const ref = useRef(null);
  const { theme } = useTheme();
  const points = useMemo(() => prepare(bars, intraday), [bars, intraday]);

  useEffect(() => {
    if (!ref.current || points.length === 0) return undefined;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: {
        background: { color: cssColor("--chart-bg", "#161b22") },
        textColor: cssColor("--chart-text", "#a7b0bf"),
        fontFamily: "Outfit, sans-serif",
      },
      grid: {
        vertLines: { color: cssColor("--chart-grid", "rgba(232, 237, 244, 0.06)") },
        horzLines: { color: cssColor("--chart-grid", "rgba(232, 237, 244, 0.06)") },
      },
      rightPriceScale: { borderColor: cssColor("--chart-axis", "rgba(232, 237, 244, 0.12)") },
      timeScale: {
        borderColor: cssColor("--chart-axis", "rgba(232, 237, 244, 0.12)"),
        timeVisible: Boolean(intraday),
        secondsVisible: false,
      },
      crosshair: {
        vertLine: {
          color: cssColor("--chart-cross", "#e0b56a"),
          labelBackgroundColor: cssColor("--chart-label", "#0c0e12"),
        },
        horzLine: {
          color: cssColor("--chart-cross", "#e0b56a"),
          labelBackgroundColor: cssColor("--chart-label", "#0c0e12"),
        },
      },
    });
    const up = cssColor("--chart-up", "#3dd68c");
    const down = cssColor("--chart-down", "#ff7b7b");
    const series = chart.addCandlestickSeries({
      upColor: up,
      downColor: down,
      borderVisible: false,
      wickUpColor: up,
      wickDownColor: down,
    });
    series.setData(points);
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [intraday, points, theme]);

  if (points.length === 0) {
    return <div className="chart chart-empty">No bars for this range.</div>;
  }
  return <div className="chart" ref={ref} />;
}
