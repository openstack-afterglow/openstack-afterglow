export interface TrafficAreaPoint {
	timestamp: number;
	rxRate: number | null;
	txRate: number | null;
}

/** Isolated rates and missing/reset intervals cannot establish a traffic segment. */
export function trafficAreaSeries(samples: TrafficAreaPoint[]) {
	const valid = (value: number | null | undefined): value is number =>
		typeof value === 'number' && Number.isFinite(value) && value >= 0;
	const first = samples[0]?.timestamp ?? 0;
	const last = samples.at(-1)?.timestamp ?? first;
	let peak = 0;
	let hasGraph = false;
	const data = samples.map((sample, index) => {
		const row: { timestamp: number; rxRate: number | null; txRate: number | null } = {
			timestamp: sample.timestamp, rxRate: null, txRate: null,
		};
		for (const direction of ['rxRate', 'txRate'] as const) {
			const value = sample[direction];
			if (!valid(value)) continue;
			peak = Math.max(peak, value);
			if (valid(samples[index - 1]?.[direction]) || valid(samples[index + 1]?.[direction])) {
				row[direction] = value;
				hasGraph = true;
			}
		}
		return row;
	});
	return { data, peak, first, last, hasGraph };
}
