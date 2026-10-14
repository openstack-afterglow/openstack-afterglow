export interface HostMetric {
	value: number | null;
	unit: '%' | 'B/s';
	series: { ts: number; value: number | null }[];
}

export type HostMetricKey = 'cpu' | 'memory' | 'disk' | 'network_rx' | 'network_tx';
export type HostObservationStatus = 'up' | 'down' | 'unknown';

export interface HostInterface {
	name: string;
	mac: string | null;
	operstate: string | null;
	addresses: string[] | null;
	rx_bytes_total: number | null;
	tx_bytes_total: number | null;
	rx_packets_total: number | null;
	tx_packets_total: number | null;
	rx_bytes_per_second: number | null;
	tx_bytes_per_second: number | null;
	rx_packets_per_second: number | null;
	tx_packets_per_second: number | null;
}

export interface MonitoredHost {
	id: string;
	name: string;
	role: 'compute' | 'controller' | 'storage';
	address: string | null;
	reachability: {
		status: HostObservationStatus;
		checked_at: string | null;
		latency_ms: number | null;
		error: string | null;
	};
	heartbeat: {
		status: HostObservationStatus;
		updated_at: string | null;
		source: string | null;
	};
	metrics: Record<HostMetricKey, HostMetric>;
	metrics_error: string | null;
	interfaces: HostInterface[] | null;
	interfaces_omitted: number | null;
}

export interface HostHealthSnapshot {
	enabled: boolean;
	interval_seconds: number;
	collected_at: string | null;
	stale: boolean;
	error: string | null;
	hosts: MonitoredHost[];
}

// Spark cannot represent gaps. Show only the latest uninterrupted observations;
// never join across a missing sample, counter reset or missed collection round.
export function continuousMetricTail(series: HostMetric['series']): number[] {
	let start = series.length;
	for (let i = series.length - 1; i >= 0; i -= 1) {
		const point = series[i];
		if (point.value === null || !Number.isFinite(point.value)) break;
		if (i < series.length - 1 && (series[i + 1].ts <= point.ts || series[i + 1].ts - point.ts > 20)) break;
		start = i;
	}
	return series.slice(start).map((point) => point.value as number);
}
