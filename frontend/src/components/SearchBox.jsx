import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDesk } from "../App";

function rank(symbols, query, limit = 8) {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  const scored = [];
  for (const item of symbols) {
    const symbol = item.symbol.toLowerCase();
    const name = item.name.toLowerCase();
    let score = 0;
    if (symbol === needle) score = 100;
    else if (symbol.startsWith(needle)) score = 80;
    else if (name.startsWith(needle)) score = 60;
    else if (symbol.includes(needle)) score = 40;
    else if (name.includes(needle)) score = 20;
    else continue;
    scored.push({ score, item });
  }
  scored.sort((a, b) => b.score - a.score || a.item.symbol.localeCompare(b.item.symbol));
  return scored.slice(0, limit).map((row) => row.item);
}

export default function SearchBox({ large = false }) {
  const { symbols, symbolCount } = useDesk();
  const navigate = useNavigate();
  const wrap = useRef(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const matches = useMemo(() => rank(symbols, query), [symbols, query]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  useEffect(() => {
    function onDoc(event) {
      if (!wrap.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function go(item) {
    if (!item) return;
    setOpen(false);
    setQuery("");
    navigate(`/stock/${encodeURIComponent(item.symbol)}`);
  }

  function onKey(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((index) => Math.min(index + 1, Math.max(matches.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(matches[active]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const listId = large ? "symbol-search-list" : "symbol-search-list-compact";

  return (
    <div className={`search ${large ? "search-large" : ""}`} ref={wrap}>
      <label className="sr" htmlFor={large ? "symbol-search" : "symbol-search-compact"}>
        Search NSE stocks by symbol or company
      </label>
      <input
        id={large ? "symbol-search" : "symbol-search-compact"}
        role="combobox"
        aria-expanded={open && matches.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        placeholder={
          symbolCount
            ? `Search ${symbolCount.toLocaleString("en-IN")} NSE stocks`
            : "Loading the NSE list…"
        }
        value={query}
        autoComplete="off"
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
      />
      {open && query.trim() && (
        <ul className="search-list" id={listId} role="listbox">
          {matches.length === 0 && <li className="search-empty">No listed equity matches that.</li>}
          {matches.map((item, index) => (
            <li key={item.symbol} role="option" aria-selected={index === active}>
              <button
                type="button"
                className={index === active ? "match active" : "match"}
                onMouseEnter={() => setActive(index)}
                onClick={() => go(item)}
              >
                <span className="match-symbol">{item.symbol}</span>
                <span className="match-name">{item.name}</span>
                {item.series && item.series !== "EQ" && <span className="tag">{item.series}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
