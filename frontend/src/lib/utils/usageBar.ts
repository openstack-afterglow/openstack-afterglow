export function formatQuota(used: number, quota: number, unit = ''): string {
	const u = unit === 'GB' ? Math.round(used) : used;
	const q = quota === -1 ? '∞' : (unit === 'GB' ? Math.round(quota) : quota);
	return `${u}/${q}${unit ? ' ' + unit : ''}`;
}

export function formatUptime(seconds: number): string {
	const d = Math.floor(seconds / 86400);
	const h = Math.floor((seconds % 86400) / 3600);
	const m = Math.floor((seconds % 3600) / 60);
	const parts: string[] = [];
	if (d > 0) parts.push(`${d}d`);
	if (h > 0) parts.push(`${h}h`);
	parts.push(`${m}m`);
	return parts.join(' ');
}
