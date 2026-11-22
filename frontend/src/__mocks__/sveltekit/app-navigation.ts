// vitest 용 $app/navigation 스텁 — 테스트에서 vi.mock('$app/navigation', ...) 으로 재정의 가능
export const goto = async (_url: string, _opts?: unknown): Promise<void> => {};
export const pushState = (_url: string, _state?: unknown): void => {};
export const replaceState = (_url: string, _state?: unknown): void => {};
export const invalidate = async (_url?: string | URL): Promise<void> => {};
export const invalidateAll = async (): Promise<void> => {};
export const beforeNavigate = (_fn: unknown): void => {};
export const afterNavigate = (_fn: unknown): void => {};
export const preloadData = async (_href: string): Promise<unknown> => undefined;
export const preloadCode = async (..._urls: string[]): Promise<void> => {};
export const disableScrollHandling = (): void => {};
export const onNavigate = (_fn: unknown): void => {};
