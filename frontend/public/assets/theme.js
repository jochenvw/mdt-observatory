(() => {
  const key = "mdt-theme";
  const valid = value => value === "light" || value === "dark";
  const query = new URLSearchParams(window.location.search).get("scoutTheme");
  const override = valid(query) ? query : null;
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  const listeners = new Set();
  let preference = null;
  let storageAvailable = true;
  try {
    const saved = window.localStorage.getItem(key);
    preference = valid(saved) ? saved : null;
  } catch {
    storageAvailable = false;
  }
  let current = override || preference || (system.matches ? "dark" : "light");
  const apply = theme => {
    current = theme;
    document.documentElement.setAttribute("data-theme", theme);
    listeners.forEach(listener => listener(theme));
  };
  apply(current);
  window.mdtTheme = {
    current: () => current,
    storageAvailable: () => storageAvailable,
    set: theme => {
      if (!valid(theme)) return false;
      preference = theme;
      try {
        window.localStorage.setItem(key, theme);
        storageAvailable = true;
      } catch {
        storageAvailable = false;
      }
      apply(theme);
      return storageAvailable;
    },
    system: () => {
      preference = null;
      try {
        window.localStorage.removeItem(key);
        storageAvailable = true;
      } catch {
        storageAvailable = false;
      }
      apply(override || (system.matches ? "dark" : "light"));
      return storageAvailable;
    },
    subscribe: listener => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
  system.addEventListener("change", () => {
    if (!preference && !override) apply(system.matches ? "dark" : "light");
  });
  window.addEventListener("storage", event => {
    if (event.key !== key && event.key !== null) return;
    preference = valid(event.newValue) ? event.newValue : null;
    apply(override || preference || (system.matches ? "dark" : "light"));
  });
})();
