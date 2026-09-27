import { createContext, useContext, useState } from "react";

export const THEME_KEY = "desk-theme";

export const THEMES = [
  { id: "dark", label: "Dark" },
  { id: "light", label: "Light" },
  { id: "midnight", label: "Midnight" },
  { id: "oled", label: "OLED" },
];

const IDS = new Set(THEMES.map((theme) => theme.id));

export function isTheme(value) {
  return IDS.has(value);
}

export function themeFromPreference() {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function readStoredTheme() {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    return isTheme(stored) ? stored : null;
  } catch {
    return null;
  }
}

export function applyTheme(id, { persist = false } = {}) {
  const theme = isTheme(id) ? id : "dark";
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme === "light" ? "light" : "dark";
  if (persist) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* private mode can block storage; the attribute still updates this visit */
    }
  }
  return theme;
}

function startingTheme() {
  const current = document.documentElement.dataset.theme;
  if (isTheme(current)) return current;
  return readStoredTheme() || themeFromPreference();
}

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(startingTheme);

  function setTheme(id) {
    setThemeState(applyTheme(id, { persist: true }));
  }

  return <ThemeContext.Provider value={{ theme, setTheme, themes: THEMES }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider");
  return value;
}
