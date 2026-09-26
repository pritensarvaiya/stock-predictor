import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { pct, prob } from "../format";

export default function Watchlist({ preview = 0 }) {
  const [data, setData] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");

  useEffect(() => {
    api.metrics().then(setMetrics).catch(() => {});
  }, []);

  useEffect(() => {
    let stop = false;
    let timer;
    async function pull() {
      try {
        const body = await api.watchlist();
        if (stop) return;
        setData(body);
        setError(body.error && body.status === "error" ? body.error : "");
        const wait = body.status === "building" || body.refreshing ? 2500 : 30000;
        timer = setTimeout(pull, wait);
      } catch (err) {
        if (!stop) {
          setError(err.message);
          timer = setTimeout(pull, 5000);
        }
      }
    }
    pull();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, []);

  const rows = data?.rows || [];
  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const filtered = needle
      ? rows.filter(
          (row) => row.symbol.toLowerCase().includes(needle) || row.name.toLowerCase().includes(needle),
        )
      : rows;
    return preview ? filtered.slice(0, preview) : filtered;
  }, [rows, filter, preview]);

  const target = metrics?.targets?.next_session_high;
  const progress = data?.progress;
  const building = !data || data.status === "building";
  const fraction = progress?.total ? Math.min(100, Math.round((progress.done / progress.total) * 100)) : 8;

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="kicker">Next session · {data?.horizon_label || "upcoming cash session"}</p>
          <h2>Chance the high prints +2%</h2>
          <p className="lede">
            {data?.definition ||
              "A hit means the next session's high is at least 2% above the reference price. It does not mean the close finishes up 2%."}
          </p>
        </div>
        <button
          type="button"
          className="text-btn"
          onClick={() => api.refreshWatchlist().then(setData).catch((err) => setError(err.message))}
        >
          Refresh scan
        </button>
      </div>

      {target && (
        <div className="reliability">
          <div>
            <span>Likely hit rate</span>
            <strong>{target.edge ? prob(target.precision_at_likely) : "Withheld"}</strong>
          </div>
          <div>
            <span>Base rate</span>
            <strong>{prob(target.base_rate)}</strong>
          </div>
          <div>
            <span>Walk-forward calls</span>
            <strong>{target.n_likely ? target.n_likely.toLocaleString("en-IN") : "—"}</strong>
          </div>
          <p>
            {target.edge
              ? "When the model said Likely, this is how often the +2% high actually printed. News is not in that test."
              : "The test did not clear a stable edge, so Likely is withheld. Rankings are still shown."}
          </p>
        </div>
      )}

      {(building || data?.refreshing) && (
        <div className="build">
          <div className="bar">
            <span style={{ width: `${fraction}%` }} />
          </div>
          <p>
            {progress?.stage === "news"
              ? `Reading news for the leading names (${progress.done}/${progress.total}).`
              : progress?.stage === "prices"
                ? `Fetching prices ${progress.done}/${progress.total}. The first scan of Nifty 200 is the slow one; after that it is cached.`
                : data?.refreshing
                  ? "Refreshing the ranking in the background. The list below is the previous scan."
                  : "Starting the Nifty 200 scan."}
          </p>
        </div>
      )}

      {error && <p className="error">{error}</p>}

      {!preview && rows.length > 0 && (
        <input
          className="filter"
          value={filter}
          placeholder="Filter the scanned names"
          onChange={(event) => setFilter(event.target.value)}
        />
      )}

      {rows.length > 0 && (
        <div className="wtable">
          <div className="whead">
            <span>#</span>
            <span>Stock</span>
            <span>Last</span>
            <span>P(+2% high)</span>
            <span>P(5-day close)</span>
            <span>Why</span>
          </div>
          {visible.map((row) => (
            <Link key={row.symbol} to={`/stock/${encodeURIComponent(row.symbol)}`} className="wrow">
              <span className="rank">{row.rank}</span>
              <span className="who">
                <strong>{row.symbol}</strong>
                <em>{row.name}</em>
              </span>
              <span className="last">
                <b>{row.price?.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</b>
                <small className={row.change_pct >= 0 ? "up" : "down"}>{pct(row.change_pct)}</small>
              </span>
              <span className="prob">
                <b>{prob(row.probability)}</b>
                <i className={`pill ${String(row.signal || "").toLowerCase()}`}>{row.signal}</i>
              </span>
              <span className="five">
                <b>{prob(row.five_day_probability)}</b>
                <small>{row.five_day_signal}</small>
              </span>
              <span className="why">
                {row.reasons?.[0]}
                {row.news_summary && <small>{row.news_label ? `${row.news_label} news. ` : ""}{row.news_summary}</small>}
              </span>
            </Link>
          ))}
        </div>
      )}

      {preview > 0 && rows.length > preview && (
        <Link className="more" to="/watchlist">
          All {rows.length} scanned names
        </Link>
      )}

      {data?.built_label && <p className="asof">Scan built {data.built_label}. Universe: {data.universe}. {data.news_scanned || 0} names include a news pass.</p>}
    </section>
  );
}
