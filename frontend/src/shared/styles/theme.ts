export type Theme = "light" | "dark";

export const THEME_KEY = "data-eyes-theme";

// Read the user's stored theme choice, falling back to the OS preference —
// shared by AppShell (which also writes it) and Login (which only reads it,
// since the toggle lives in the topbar, not on the auth screen).
export function getInitialTheme(): Theme {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
