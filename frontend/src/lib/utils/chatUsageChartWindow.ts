import { t } from '$lib/i18n/ns/chat-settings';

export type UsageChartBucket = '5m' | '15m' | 'hour' | 'day' | 'month';

export interface UsageChartWindow {
	milliseconds: number;
	label: string;
}

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

const WINDOWS: Partial<Record<UsageChartBucket, UsageChartWindow>> = {
	'5m': { milliseconds: 4 * HOUR, get label() { return t('chartWindow.lastFourHours'); } },
	'15m': { milliseconds: 12 * HOUR, get label() { return t('chartWindow.lastTwelveHours'); } },
	hour: { milliseconds: 48 * HOUR, get label() { return t('chartWindow.lastFortyEightHours'); } },
	day: { milliseconds: 30 * DAY, get label() { return t('chartWindow.lastThirtyDays'); } }
};

export function usageChartWindow(bucket: string): UsageChartWindow | null {
	return WINDOWS[bucket as UsageChartBucket] ?? null;
}
