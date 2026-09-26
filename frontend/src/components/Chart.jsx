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
        background: { color: "#fffdf8" },
        textColor: "#6f675e",
        fontFamily: "Outfit, sans-serif",
      },
      grid: {
        vertLines: { color: "#f3eee6" },
        horzLines: { color: "#f3eee6" },
      },
      rightPriceScale: { borderColor: "#e3dacb" },
      timeScale: {
        borderColor: "#e3dacb",
        timeVisible: Boolean(intraday),
        secondsVisible: false,
      },
      crosshair: { vertLine: { color: "#c4622d", labelBackgroundColor: "#1c1915" }, horzLine: { color: "#c4622d", labelBackgroundColor: "#1c1915" } },
    });
    const series = chart.addCandlestickSeries({
      upColor: "#0d6e5b",
      downColor: "#a33b2b",
      borderVisible: false,
      wickUpColor: "#0d6e5b",
      wickDownColor: "#a33b2b",
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
