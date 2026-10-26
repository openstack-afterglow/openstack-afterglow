/** Display-only retention within one mounted, scope-owned controller. */
export function createSwr(getScope: () => string | null | undefined) {
  const entries = new Map<string, { data: unknown; expiresAt: number }>();
  let scope = getScope();
  function synchronizeScope() {
    const next = getScope();
    if (next !== scope) { entries.clear(); scope = next; }
  }
  function swrGet<T>(path: string): T | null {
    synchronizeScope();
    const entry = entries.get(path);
    if (!entry || entry.expiresAt <= Date.now()) { entries.delete(path); return null; }
    return entry.data as T;
  }
  function swrSet(path: string, data: unknown) {
    synchronizeScope();
    entries.set(path, { data, expiresAt: Date.now() + 30_000 });
  }
  return { swrGet, swrSet };
}
