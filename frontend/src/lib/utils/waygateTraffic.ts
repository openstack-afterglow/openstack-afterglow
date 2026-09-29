import type { WaygateClient } from '$lib/types/waygate';

export const WAYGATE_TRAFFIC_LIMIT = 60;
/** Legacy user workspace does not supply cadence; retain its upstream 90-second window. */
export const WAYGATE_TRAFFIC_STALE_MS = 90_000;
/** Old gateway images report on the 15-second reconcile cycle without cadence metadata. */
const LEGACY_REPORT_INTERVAL_SECONDS = 15;

export function waygateTrafficFreshnessMs(reportIntervalSeconds: number | null | undefined, pollIntervalSeconds: number): number {
	const report = typeof reportIntervalSeconds === 'number' && Number.isInteger(reportIntervalSeconds) && reportIntervalSeconds >= 1 && reportIntervalSeconds <= 60
		? reportIntervalSeconds : LEGACY_REPORT_INTERVAL_SECONDS;
	return Math.max(5, 3 * Math.max(report, pollIntervalSeconds)) * 1000;
}

/** Byte counters and rates are client-perspective: RX is data the client downloaded. */
export interface ClientTrafficSample {
	timestamp: number;
	receivedAt: number;
	rxBytes: number | null;
	txBytes: number | null;
	rxRate: number | null;
	txRate: number | null;
}

export interface ClientTrafficHistory {
	samples: ClientTrafficSample[];
	reportAvailable: boolean;
}

type Report = Pick<WaygateClient, 'rx_bytes' | 'tx_bytes' | 'last_reported_at'>;

export function trafficCounter(value: number | null | undefined): number | null {
	return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

/**
 * Waygate reports gateway-perspective peer counters. The client receives what the
 * gateway transmits, so client RX is `tx_bytes` and client TX is `rx_bytes`.
 */
export function clientTrafficTotals(report: Pick<WaygateClient, 'rx_bytes' | 'tx_bytes'>) {
	return { rxBytes: trafficCounter(report.tx_bytes), txBytes: trafficCounter(report.rx_bytes) };
}

/**
 * Appends one server-timestamped status report. Server receipt timestamps drive
 * deltas, so browser clock skew never changes a rate; browser receipt time only
 * decides whether reports stopped arriving.
 */
export function appendClientTraffic(
	history: ClientTrafficHistory | undefined,
	report: Report,
	now: number,
	freshnessMs = WAYGATE_TRAFFIC_STALE_MS
): ClientTrafficHistory {
	const previous = history ?? { samples: [], reportAvailable: false };
	const timestamp = report.last_reported_at ? Date.parse(report.last_reported_at) : NaN;
	if (!Number.isFinite(timestamp)) return previous.reportAvailable ? { samples: previous.samples, reportAvailable: false } : previous;
	const last = previous.samples.at(-1);
	// Repeated polling and delayed reports never create extra points or deltas.
	if (last && timestamp <= last.timestamp) return previous;
	const { rxBytes, txBytes } = clientTrafficTotals(report);
	const elapsed = last ? timestamp - last.timestamp : 0;
	const reset = !!last && (
		(rxBytes !== null && last.rxBytes !== null && rxBytes < last.rxBytes) ||
		(txBytes !== null && last.txBytes !== null && txBytes < last.txBytes)
	);
	const contiguous = !!last && previous.reportAvailable && elapsed <= freshnessMs && !reset;
	const rate = (current: number | null, before: number | null | undefined) =>
		contiguous && current !== null && before != null ? (current - before) / (elapsed / 1000) : null;
	return {
		samples: [
			...previous.samples.slice(-(WAYGATE_TRAFFIC_LIMIT - 1)),
			{
				timestamp,
				receivedAt: now,
				rxBytes,
				txBytes,
				rxRate: rate(rxBytes, last?.rxBytes),
				txRate: rate(txBytes, last?.txBytes),
			},
		],
		reportAvailable: rxBytes !== null || txBytes !== null,
	};
}

export function currentClientTraffic(history: ClientTrafficHistory | undefined, now: number, freshnessMs = WAYGATE_TRAFFIC_STALE_MS) {
	const last = history?.samples.at(-1);
	// Cached reports continue aging after arrival; polling never extends their freshness.
	const fresh = !!last && !!history?.reportAvailable &&
		now - last.receivedAt <= freshnessMs &&
		now >= last.timestamp && now - last.timestamp <= freshnessMs;
	return {
		fresh,
		rxRate: fresh ? last.rxRate : null,
		txRate: fresh ? last.txRate : null,
	};
}

/** Binary byte units, shared by totals and bytes/second rates. Missing is not zero. */
export function formatTrafficBytes(value: number | null | undefined): string {
	if (value == null || !Number.isFinite(value) || value < 0) return '—';
	const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
	const unit = value < 1 ? 0 : Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
	return `${(value / 1024 ** unit).toLocaleString('ko', { maximumFractionDigits: unit === 0 ? 0 : 1 })} ${units[unit]}`;
}
