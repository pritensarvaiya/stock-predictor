import { createChart } from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";

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

export default function PriceChart({ bars, intraday }) {
  const ref = useRef(null);
  const points = useMemo(() => prepare(bars, intraday), [bars, intraday]);

  useEffect(() => {
    if (!ref.current || points.length === 0) return undefined;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: {
        background: { color: "#161b22" },
        textColor: "#a7b0bf",
        fontFamily: "Outfit, sans-serif",
      },
      grid: {
        vertLines: { color: "rgba(232, 237, 244, 0.06)" },
        horzLines: { color: "rgba(232, 237, 244, 0.06)" },
      },
      rightPriceScale: { borderColor: "rgba(232, 237, 244, 0.12)" },
      timeScale: {
        borderColor: "rgba(232, 237, 244, 0.12)",
        timeVisible: Boolean(intraday),
        secondsVisible: false,
      },
      crosshair: {
        vertLine: { color: "#e0b56a", labelBackgroundColor: "#0c0e12" },
        horzLine: { color: "#e0b56a", labelBackgroundColor: "#0c0e12" },
      },
    });
    const series = chart.addCandlestickSeries({
      upColor: "#3dd68c",
      downColor: "#ff7b7b",
      borderVisible: false,
      wickUpColor: "#3dd68c",
      wickDownColor: "#ff7b7b",
    });
    series.setData(points);
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [intraday, points]);

  if (points.length === 0) {
    return <div className="chart chart-empty">No bars for this range.</div>;
  }
  return <div className="chart" ref={ref} />;
}
