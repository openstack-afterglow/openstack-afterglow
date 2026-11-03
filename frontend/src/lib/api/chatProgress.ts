/** Match the server's 1–4000 Unicode-code-point bound without trimming output. */
export function isBoundedToolProgress(value: unknown): value is string {
	return typeof value === 'string' && /^[\s\S]{1,4000}$/u.test(value);
}
