import { useEffect, useState } from "react";
import { api } from "../api";
import { prob } from "../format";

function num(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
}

export default function Method() {
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.metrics().then(setMetrics).catch((err) => setError(err.message));
  }, []);

  const primary = metrics?.targets?.next_session_high;
  const secondary = metrics?.targets?.five_day_close;

  return (
    <article className="page method">
      <p className="kicker">How the number is made</p>
      <h1>A probability, measured on dates the model had not seen.</h1>
      <p className="lede">
        Desk fits a regularised logistic regression on daily technical features and the Nifty 50 trend,
        then calibrates the probabilities on a later slice of that training window. The hit rate on this
        page is not the fit on those training days. Each test fold was scored by a model trained only on
        earlier dates. The copy running live is refit on the full labeled sample with the same recipe.
      </p>
      {error && <p className="error">{error}</p>}
      {!metrics && !error && <p>Loading the measured results…</p>}
      {metrics && (
        <>
          <section className="panel">
            <h2>What a hit means</h2>
            <div className="defs">
              <div>
                <h3>{primary.name}</h3>
                <p>{primary.definition}</p>
                <p>
                  This is the number on the watchlist. Because it is an intraday high, volatile names reach
                  it more often even if they do not close higher.
                </p>
              </div>
              <div>
                <h3>{secondary.name}</h3>
                <p>{secondary.definition}</p>
                <p>This is the closer thing to “the stock is up 2% within a week of sessions.”</p>
              </div>
            </div>
            <p className="note">
              Reference price: the latest close when the cash market is shut, which matches the backtest.
              While the session is open, the reference is the latest trade, and that reading sits a step
              outside the test. Universe: {metrics.universe}, {metrics.n_symbols} symbols,{" "}
              {metrics.date_start} to {metrics.date_end}. News was not in the backtest. Live, headlines can
              nudge a probability by at most 5 points.
            </p>
          </section>

          <TargetTable title="Next-session high" target={primary} />
          <TargetTable title="Five-session close" target={secondary} />

          <section className="panel">
            <h2>What the model can see</h2>
            <p>
              Returns over 1, 5, 10, and 20 sessions, RSI, MACD histogram, distance from the 20- and 50-day
              averages, ATR, volume versus its recent average, the opening gap and its 5-session average,
              distance from the 20-day high, where the close sat in the day’s range, and the same kind of
              trend measures for the Nifty 50. Prices used for features are split-adjusted. The chart and
              the quote show the traded price.
            </p>
            <p>{metrics.note}</p>
            <h3>Largest standardised coefficients · next-session high</h3>
            <p className="note">
              A positive coefficient means a higher-than-usual reading of that feature raised the chance
              in the fitted model. It is an association in this sample, not a law.
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Feature</th>
                    <th>Coefficient</th>
                  </tr>
                </thead>
                <tbody>
                  {(primary.coefficients || []).slice(0, 8).map((row) => (
                    <tr key={row.key}>
                      <td>{row.label}</td>
                      <td className={row.coefficient >= 0 ? "up" : "down"}>{num(row.coefficient, 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <h2>News</h2>
            <p>
              Headlines come from the Google News RSS search for the company, plus recent NSE corporate
              announcements when the exchange returns them. If <code>GEMINI_API_KEY</code> is set, Gemini
              ({metrics.gemini_model || "gemini-3.1-flash-lite, unless GEMINI_MODEL overrides it"}) writes
              the summary and a price-impact rating. With no key, Desk uses VADER plus a short list of
              finance phrases. That fallback is a word list. It will miss sarcasm and context.
            </p>
          </section>
        </>
      )}
    </article>
  );
}

function TargetTable({ title, target }) {
  if (!target) return null;
  return (
    <section className="panel">
      <h2>{title}</h2>
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
          <span>AUC</span>
          <strong>{num(target.pooled?.auc, 3)}</strong>
        </div>
        <div>
          <span>Brier</span>
          <strong>{num(target.pooled?.brier, 3)}</strong>
        </div>
        <p>
          Likely means a calibrated probability at or above {prob(target.likely_threshold)}. Unlikely means
          at or below {prob(target.unlikely_threshold)}. Everything between is Uncertain. Test rows:{" "}
          {target.pooled?.n?.toLocaleString("en-IN")}. Mean predicted probability {prob(target.pooled?.mean_predicted)}.
        </p>
      </div>
      <h3>Walk-forward folds</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Test window</th>
              <th>Rows</th>
              <th>Base rate</th>
              <th>Likely calls</th>
              <th>Hit rate</th>
              <th>AUC</th>
            </tr>
          </thead>
          <tbody>
            {(target.folds || []).map((fold) => (
              <tr key={fold.test_start}>
                <td>
                  {fold.test_start} → {fold.test_end}
                </td>
                <td>{fold.n?.toLocaleString("en-IN")}</td>
                <td>{prob(fold.base_rate)}</td>
                <td>{fold.n_likely?.toLocaleString("en-IN")}</td>
                <td>{fold.precision_at_likely == null ? "—" : prob(fold.precision_at_likely)}</td>
                <td>{num(fold.auc, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Calibration by predicted-probability decile</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Predicted bin</th>
              <th>Rows</th>
              <th>Mean predicted</th>
              <th>Realized</th>
            </tr>
          </thead>
          <tbody>
            {(target.deciles || []).map((row) => (
              <tr key={row.bin}>
                <td>{row.bin}</td>
                <td>{row.n.toLocaleString("en-IN")}</td>
                <td>{prob(row.mean_predicted)}</td>
                <td>{prob(row.realized)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
