import { createContext, useContext, useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { api } from "./api";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import Method from "./pages/Method";
import Stock from "./pages/Stock";
import WatchlistPage from "./pages/WatchlistPage";

const DeskContext = createContext(null);

export function useDesk() {
  return useContext(DeskContext);
}

export default function App() {
  const [symbols, setSymbols] = useState([]);
  const [symbolSource, setSymbolSource] = useState("");
  const [symbolCount, setSymbolCount] = useState(0);
  const [market, setMarket] = useState(null);

  useEffect(() => {
    api
      .symbols()
      .then((data) => {
        setSymbols(data.symbols || []);
        setSymbolSource(data.source || "");
        setSymbolCount(data.count || (data.symbols || []).length);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    let stop = false;
    async function pull() {
      try {
        const status = await api.market();
        if (!stop) setMarket(status);
      } catch {
        /* the page still renders; the next poll retries */
      }
    }
    pull();
    const id = setInterval(pull, 60_000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, []);

  return (
    <DeskContext.Provider value={{ symbols, symbolSource, symbolCount, market }}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="/watchlist" element={<WatchlistPage />} />
            <Route path="/stock/:symbol" element={<Stock />} />
            <Route path="/method" element={<Method />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </DeskContext.Provider>
  );
}
