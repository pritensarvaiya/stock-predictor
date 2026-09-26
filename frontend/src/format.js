export function inr(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

export function money(value, currency = "INR") {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

export function pct(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const signed = value > 0 ? "+" : "";
  return `${signed}${(value * 100).toFixed(digits)}%`;
}

export function prob(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Math.round(value * 100)}%`;
}

export function when(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function compactNumber(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function points(value) {
  if (value == null || Math.abs(value) < 0.005) return "no news nudge";
  const sign = value > 0 ? "+" : "−";
  return `${sign}${Math.round(Math.abs(value) * 100)} pt news nudge`;
}
