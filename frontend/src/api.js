function errorMessage(body, status) {
  if (body && typeof body.detail === "string") return body.detail;
  if (body && Array.isArray(body.detail)) return body.detail.map((item) => item.msg || "").join(" ");
  return `Request failed (${status})`;
}

async function get(path) {
  const response = await fetch(path);
  if (response.status === 401) {
    const next = window.location.pathname + window.location.search;
    window.location.assign(`/login?next=${encodeURIComponent(next)}`);
    throw new Error("Sign in required");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorMessage(body, response.status));
  return body;
}

export const api = {
  market: () => get("/api/market"),
  symbols: () => get("/api/symbols"),
  stock: (symbol, exchange) => get(`/api/stock/${encodeURIComponent(symbol)}?exchange=${exchange}`),
  quote: (symbol, exchange) => get(`/api/quote/${encodeURIComponent(symbol)}?exchange=${exchange}`),
  news: (symbol, exchange) => get(`/api/news/${encodeURIComponent(symbol)}?exchange=${exchange}`),
  chart: (symbol, range, exchange) =>
    get(`/api/chart/${encodeURIComponent(symbol)}?range=${range}&exchange=${exchange}`),
  predict: (symbol, exchange) => get(`/api/predict/${encodeURIComponent(symbol)}?exchange=${exchange}`),
  watchlist: () => get("/api/watchlist"),
  refreshWatchlist: async () => {
    const response = await fetch("/api/watchlist/refresh", { method: "POST" });
    if (response.status === 401) {
      const next = window.location.pathname + window.location.search;
      window.location.assign(`/login?next=${encodeURIComponent(next)}`);
      throw new Error("Sign in required");
    }
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(errorMessage(body, response.status));
    return body;
  },
  metrics: () => get("/api/metrics"),
};
