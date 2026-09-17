import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { describe, expect, it, vi } from 'vitest';
import type { ThemeController } from './theme';

const script = readFileSync(new URL('../public/assets/theme.js', import.meta.url), 'utf8');
function boot({ query = '', saved = null, dark = false, blocked = false }: { query?: string; saved?: string | null; dark?: boolean; blocked?: boolean } = {}) {
  const values = new Map<string, string>();
  if (saved !== null) values.set('mdt-theme', saved);
  const attributes = new Map<string, string>();
  let systemListener = () => {};
  let storageListener = (_event: { key: string | null; newValue: string | null }) => {};
  const storage = {
    getItem: vi.fn((key: string) => { if (blocked) throw new Error('Storage disabled'); return values.get(key) ?? null; }),
    setItem: vi.fn((key: string, value: string) => { if (blocked) throw new Error('Storage disabled'); values.set(key, value); }),
    removeItem: vi.fn((key: string) => { if (blocked) throw new Error('Storage disabled'); values.delete(key); }),
  };
  const system = { matches: dark, addEventListener: (_name: string, listener: () => void) => { systemListener = listener; } };
  const window = {
    location: { search: query }, localStorage: storage, matchMedia: () => system,
    addEventListener: (_name: string, listener: typeof storageListener) => { storageListener = listener; },
    mdtTheme: undefined as ThemeController | undefined,
  };
  runInNewContext(script, { window, document: { documentElement: { setAttribute: (key: string, value: string) => attributes.set(key, value) } }, URLSearchParams });
  if (!window.mdtTheme) throw new Error('Pre-paint theme controller was not installed');
  return { controller: window.mdtTheme, attributes, values, storage, system, systemChanged: () => systemListener(), storageChanged: storageListener };
}
describe('pre-paint persistent theme', () => {
  it.each([false, true])('uses system appearance when no explicit preference exists (%s)', dark => {
    expect(boot({ dark }).attributes.get('data-theme')).toBe(dark ? 'dark' : 'light');
  });
  it('gives a valid URL override precedence over saved and system preferences', () => {
    expect(boot({ query: '?scoutTheme=light', saved: 'dark', dark: true }).controller.current()).toBe('light');
    expect(boot({ query: '?scoutTheme=dark', saved: 'light' }).controller.current()).toBe('dark');
  });
  it('rejects invalid URL and storage values', () => {
    expect(boot({ query: '?scoutTheme=invalid', saved: 'dark' }).controller.current()).toBe('dark');
    expect(boot({ query: '?scoutTheme=invalid', saved: 'not-a-theme', dark: true }).controller.current()).toBe('dark');
  });
  it('persists explicit choices and restores them on a new page', () => {
    const page = boot();
    expect(page.controller.set('dark')).toBe(true);
    expect(page.attributes.get('data-theme')).toBe('dark');
    expect(boot({ saved: page.values.get('mdt-theme') }).controller.current()).toBe('dark');
  });
  it('continues to apply an accessible theme when storage is unavailable', () => {
    const page = boot({ blocked: true, dark: true });
    expect(page.controller.current()).toBe('dark');
    expect(page.controller.storageAvailable()).toBe(false);
    expect(page.controller.set('light')).toBe(false);
    expect(page.attributes.get('data-theme')).toBe('light');
  });
  it('follows system changes only without an explicit choice', () => {
    const page = boot();
    page.system.matches = true;
    page.systemChanged();
    expect(page.controller.current()).toBe('dark');
    page.controller.set('light');
    page.systemChanged();
    expect(page.controller.current()).toBe('light');
    page.controller.system();
    expect(page.values.has('mdt-theme')).toBe(false);
    expect(page.controller.current()).toBe('dark');
  });
  it('synchronizes tabs, respects URL precedence and unsubscribes listeners', () => {
    const page = boot();
    const listener = vi.fn();
    const unsubscribe = page.controller.subscribe(listener);
    page.storageChanged({ key: 'mdt-theme', newValue: 'dark' });
    expect(listener).toHaveBeenCalledWith('dark');
    unsubscribe();
    page.storageChanged({ key: 'mdt-theme', newValue: 'light' });
    expect(listener).toHaveBeenCalledTimes(1);
    const overridden = boot({ query: '?scoutTheme=light' });
    overridden.storageChanged({ key: 'mdt-theme', newValue: 'dark' });
    expect(overridden.controller.current()).toBe('light');
  });
});
