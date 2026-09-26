import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useDesk } from "../App";
import SearchBox from "./SearchBox";

export default function Layout() {
  const { market } = useDesk();
  const { pathname } = useLocation();
  const open = Boolean(market?.is_open);
  const showCompactSearch = pathname !== "/";

  return (
    <div className="shell">
      <header className="top">
        <div className="brand-row">
          <NavLink to="/" className="brand">
            <span className="mark" aria-hidden="true" />
            <span>
              <strong>Desk</strong>
              <small>NSE · Asia/Kolkata</small>
            </span>
          </NavLink>
          <nav>
            <NavLink to="/watchlist">Watchlist</NavLink>
            <NavLink to="/method">Method</NavLink>
          </nav>
          <div className={`session ${open ? "open" : "closed"}`}>
            <b>{open ? "Market open" : "Market closed"}</b>
            <span>
              {market
                ? `${market.reason} · next session ${market.next_session_label}, 9:15 IST`
                : "Checking the session clock"}
            </span>
          </div>
        </div>
        {showCompactSearch && <SearchBox />}
      </header>
      <main>
        <Outlet />
      </main>
      <footer>
        <p>
          Probabilities only. Desk can be wrong, and a Likely reading is not a prediction that the
          move will happen. This is not financial advice and not a recommendation to buy or sell.
        </p>
        <p className="sources">
          Listings from NSE EQUITY_L. Prices from Yahoo Finance, often delayed about 15 minutes.
          News from Google News and NSE announcements. Index membership from Nifty Indices.
        </p>
      </footer>
    </div>
  );
}
