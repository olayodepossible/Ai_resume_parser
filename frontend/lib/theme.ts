import type { Theme } from "./types";

export const THEME_STORAGE_KEY = "cvparser.theme";

/**
 * Add or remove `.dark` on <html>, which is what `globals.css` keys its
 * `dark:` variant off.
 *
 * The choice is also mirrored into localStorage so `ThemeScript` can restore
 * it before first paint — the authoritative copy lives on the user record and
 * arrives too late to prevent a flash.
 */
export function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;

  const dark =
    theme === "dark" ||
    (theme === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);

  document.documentElement.classList.toggle("dark", dark);

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Private-browsing modes can refuse writes; the class is already applied.
  }
}

/**
 * Inlined into <head> and run before the first paint, so a returning dark-mode
 * user never sees a white flash. Deliberately dependency-free and defensive:
 * it runs before React and must not throw.
 */
export const THEME_BOOTSTRAP_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)}) || "system";
    var dark = stored === "dark" || (stored === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
  } catch (error) {}
})();
`.trim();
