import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import PriceChart from "../components/Chart";
import { compactNumber, money, pct, points, prob, when } from "../format";

const RANGES = ["1D", "1W", "1M", "6M", "1Y", "5Y"];

export default function Stock() {
  const { symbol } = useParams();
  const [params, setParams] = useSearchParams();
  const exchange = (params.get("exchange") || "NSE").toUpperCase();
  const [data, setData] = useState(null);
  const [chart, setChart] = useState(null);
  const [range, setRange] = useState("6M");
  const [error, setError] = useState("");
  const [chartError, setChartError] = useState("");

  useEffect(() => {
    let stop = false;
    setData(null);
    setError("");
    api
      .stock(symbol, exchange)
      .then((body) => {
        if (!stop) setData(body);
      })
      .catch((err) => {
        if (!stop) setError(err.message);
      });
    return () => {
      stop = true;
    };
  }, [symbol, exchange]);

  useEffect(() => {
    let stop = false;
    setChartError("");
    api
      .chart(symbol, range, exchange)
      .then((body) => {
        if (!stop) setChart(body);
      })
      .catch((err) => {
        if (!stop) setChartError(err.message);
      });
    return () => {
      stop = true;
    };
  }, [symbol, exchange, range]);

  useEffect(() => {
    if (!data?.quote?.market?.is_open) return undefined;
    const quoteTimer = setInterval(() => {
      api.quote(symbol, exchange).then((quote) => {
        setData((current) => (current ? { ...current, quote } : current));
      }).catch(() => {});
    }, 45_000);
    const predictTimer = setInterval(() => {
      api.predict(symbol, exchange).then((prediction) => {
        setData((current) => (current ? { ...current, prediction } : current));
      }).catch(() => {});
    }, 180_000);
    const chartTimer =
      range === "1D"
        ? setInterval(() => {
            api.chart(symbol, range, exchange).then(setChart).catch(() => {});
          }, 60_000)
        : null;
    return () => {
      clearInterval(quoteTimer);
      clearInterval(predictTimer);
      if (chartTimer) clearInterval(chartTimer);
    };
  }, [data?.quote?.market?.is_open, symbol, exchange, range]);

  function setExchange(next) {
    const copy = new URLSearchParams(params);
    if (next === "NSE") copy.delete("exchange");
    else copy.set("exchange", next);
    setParams(copy);
  }

  const quote = data?.quote;
  const prediction = data?.prediction;
  const news = data?.news;
  const up = (quote?.change_pct || 0) >= 0;

  return (
    <article className="stock">
      <Link className="back" to="/">
        All stocks
      </Link>
      <header className="stock-head">
        <div>
          <p className="kicker">
            {exchange}
            {quote?.series ? ` · ${quote.series}` : ""}
            {quote?.isin ? ` · ${quote.isin}` : ""}
          </p>
          <h1>{symbol}</h1>
          <p className="company">{quote?.name || "Loading…"}</p>
        </div>
        <div className="segment" role="group" aria-label="Exchange">
          {["NSE", "BSE"].map((item) => (
            <button key={item} type="button" className={exchange === item ? "on" : ""} onClick={() => setExchange(item)}>
              {item}
            </button>
          ))}
        </div>
      </header>

      {error && <p className="error">{error}</p>}

      {quote?.price != null && (
        <div className="price-row">
          <div className="price">
            <strong>{money(quote.price, quote.currency)}</strong>
            <span className={up ? "up" : "down"}>
              {pct(quote.change_pct)} {quote.change != null ? `(${money(quote.change, quote.currency)})` : ""}
            </span>
          </div>
          <dl className="facts">
            <div>
              <dt>Previous close</dt>
              <dd>{money(quote.previous_close, quote.currency)}</dd>
            </div>
            <div>
              <dt>Day range</dt>
              <dd>
                {money(quote.day_low, quote.currency)} – {money(quote.day_high, quote.currency)}
              </dd>
            </div>
            <div>
              <dt>Volume</dt>
              <dd>{compactNumber(quote.volume)}</dd>
            </div>
          </dl>
          <p className="delay">{quote.delay_note}</p>
          {quote.market?.is_open && <p className="delay">This page refreshes the price about every minute while the session is open.</p>}
        </div>
      )}

      <div className="stock-grid">
        <div className="stack">
          <section className="panel">
            <div className="ranges" role="tablist" aria-label="Chart range">
              {RANGES.map((item) => (
                <button
                  key={item}
                  type="button"
                  role="tab"
                  aria-selected={range === item}
                  className={range === item ? "on" : ""}
                  onClick={() => setRange(item)}
                >
                  {item}
                </button>
              ))}
            </div>
            {chartError && <p className="error">{chartError}</p>}
            <PriceChart bars={chart?.bars} intraday={chart?.intraday} />
            <p className="asof">
              {chart?.delay_note}
              {chart?.intraday ? " Intraday times are India time (IST)." : ""}
            </p>
          </section>

          <section className="panel">
            <div className="panel-head">
              <div>
                <p className="kicker">News and filings</p>
                <h2>What crossed recently</h2>
              </div>
              {news?.sentiment && (
                <span className={`pill ${news.sentiment.label || "neutral"}`}>
                  {news.sentiment.method === "gemini" ? `Gemini · ${news.sentiment.model}` : "Word list"}
                  {" · "}
                  {news.sentiment.label}
                </span>
              )}
            </div>
            {news?.sentiment?.summary && <p className="lede">{news.sentiment.summary}</p>}
            <ul className="headlines">
              {(news?.items || []).map((item) => (
                <li key={item.url + item.title}>
                  <a href={item.url} target="_blank" rel="noreferrer">
                    {item.title}
                  </a>
                  <small>
                    {item.source}
                    {item.kind === "announcement" ? " · filing" : ""}
                    {item.published ? ` · ${when(item.published)}` : ""}
                  </small>
                </li>
              ))}
              {news && news.items?.length === 0 && <li className="search-empty">No recent headlines or filings came back.</li>}
            </ul>
          </section>
        </div>

        <aside className="stack">
          {prediction && (
            <section className="panel predict">
              <p className="kicker">Next session · {prediction.horizon_label}</p>
              <h2>{prediction.primary.name}</h2>
              <div className="big-prob">
                <strong>{prob(prediction.primary.probability)}</strong>
                <span className={`pill ${prediction.primary.signal.toLowerCase()}`}>{prediction.primary.signal}</span>
              </div>
              <p className="definition">{prediction.primary.definition}</p>
              <p className="compare">
                Model {prob(prediction.primary.model_probability)} before news · {points(prediction.primary.news_nudge)}.{" "}
                {prediction.primary.comparison}
              </p>
              <ul className="drivers">
                {prediction.drivers.map((driver) => (
                  <li key={driver.key} className={driver.direction}>
                    {driver.sentence}
                  </li>
                ))}
              </ul>
              {prediction.tail_note && <p className="tail">{prediction.tail_note}</p>}
              {prediction.volatility_note && <p className="note">{prediction.volatility_note}</p>}
              <p className="note">{prediction.market_context}</p>
              <div className="secondary">
                <div>
                  <span>{prediction.secondary.name}</span>
                  <strong>{prob(prediction.secondary.probability)}</strong>
                </div>
                <p>
                  {prediction.secondary.definition} Signal: {prediction.secondary.signal}. Base rate{" "}
                  {prob(prediction.secondary.base_rate)}.
                </p>
              </div>
              <div className="reliability tight">
                <div>
                  <span>Historical Likely hit rate</span>
                  <strong>
                    {prediction.reliability.edge ? prob(prediction.reliability.hit_rate) : "Withheld"}
                  </strong>
                </div>
                <div>
                  <span>Base rate</span>
                  <strong>{prob(prediction.reliability.base_rate)}</strong>
                </div>
                <p>{prediction.reliability.sentence}</p>
              </div>
              <p className="disclaimer">{prediction.disclaimer}</p>
            </section>
          )}
          {!prediction && !error && <section className="panel">Scoring {symbol}…</section>}
        </aside>
      </div>
    </article>
  );
}
