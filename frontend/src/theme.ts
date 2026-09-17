import { useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';
export interface ThemeController {
  current(): Theme;
  storageAvailable(): boolean;
  set(theme: Theme): boolean;
  system(): boolean;
  subscribe(listener: (theme: Theme) => void): () => void;
}
declare global {
  interface Window { mdtTheme: ThemeController }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => window.mdtTheme.current());
  const [saved, setSaved] = useState(() => window.mdtTheme.storageAvailable());
  useEffect(() => window.mdtTheme.subscribe(setTheme), []);
  return {
    theme,
    saved,
    toggle: () => setSaved(window.mdtTheme.set(theme === 'dark' ? 'light' : 'dark')),
    useSystem: () => setSaved(window.mdtTheme.system()),
  };
}
