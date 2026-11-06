
export function serviceTimestamp(value: string | null | undefined): number | null {
	if (!value) return null;
	const normalized = value.replace(' ', 'T');
	// OpenStack timestamps without an explicit offset are UTC, not browser-local time.
	const timestamp = Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized) ? normalized : `${normalized}Z`);
	return Number.isFinite(timestamp) ? timestamp : null;
}
