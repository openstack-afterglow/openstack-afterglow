// Only server-issued, secret-free source identifiers may survive sign-in.
// Do not decode arbitrary paths or accept a generic redirect URL.
const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const SOURCE_PATH = new RegExp(`^/lumen/sources/(?:assets/${UUID}|runs/[A-Za-z0-9_-]{1,200}/[A-Za-z0-9_-]{1,200})$`);
export const LUMEN_SOURCE_QUERY = 'lumen_source';
export function safeLumenSourcePath(value: unknown): string | null {
	return typeof value === 'string' && SOURCE_PATH.exec(value)?.[0] === value ? value : null;
}
export function lumenSourceLoginPath(pathname: string): string {
	const source = safeLumenSourcePath(pathname);
	return source ? `/login?${LUMEN_SOURCE_QUERY}=${encodeURIComponent(source)}` : '/login';
}
