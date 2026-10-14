import { intlLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/traffic-analytics';
import type { TrafficMetric } from '$lib/types/trafficAnalytics';

export function formatTrafficValue(value: number | null, metric?: TrafficMetric): string {
	if (value === null) return t('unknown');
	const locale = intlLocale();
	if (metric === 'request_bytes' || metric === 'response_bytes') {
		const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
		const power = value > 0 ? Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024))) : 0;
		return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value / 1024 ** power)} ${units[power]}`;
	}
	const formatted = new Intl.NumberFormat(locale, { maximumFractionDigits: metric?.startsWith('latency') ? 2 : 0 }).format(value);
	return metric?.startsWith('latency') ? `${formatted} ms` : formatted;
}
export function trafficCountryName(code: string): string {
	if (code === 'XX') return t('map.unknown');
	try { return new Intl.DisplayNames([intlLocale()], { type: 'region' }).of(code) ?? code; }
	catch { return code; }
}
export function formatTrafficTime(at: number | null): string {
	return at === null ? t('unknown') : new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(at * 1000));
}
