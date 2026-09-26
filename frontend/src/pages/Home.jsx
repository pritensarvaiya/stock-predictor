import { useDesk } from "../App";
import SearchBox from "../components/SearchBox";
import Watchlist from "../components/Watchlist";

export default function Home() {
  const { market, symbolCount, symbolSource } = useDesk();
  const open = Boolean(market?.is_open);

  return (
    <div className="home">
      <section className="hero">
        <p className="kicker">{open ? "Session underway" : "Cash market closed"}</p>
        <h1>{open ? "Look up a stock, or scan the next session." : "Next session watchlist"}</h1>
        <p className="lede">
          {market
            ? `${market.reason}. The model is aimed at the ${market.next_session_label} session, which opens at 9:15 IST.`
            : "Checking NSE hours and holidays."}{" "}
          {symbolCount
            ? `Search covers ${symbolCount.toLocaleString("en-IN")} equities from ${symbolSource}.`
            : "The equity list is loading."}
        </p>
        <SearchBox large />
      </section>
      <Watchlist preview={8} />
    </div>
  );
}
