export interface TrafficAreaPoint {
	timestamp: number;
	rxRate: number | null;
	txRate: number | null;
}

/** No interpolation across missing samples; both directions share a zero-based axis. */
export function trafficAreaGeometry(samples: TrafficAreaPoint[]) {
	const width = 300;
	const height = 64;
	const first = samples[0]?.timestamp ?? 0;
	const last = samples.at(-1)?.timestamp ?? first;
	const peak = samples.reduce((max, sample) => Math.max(max, sample.rxRate ?? 0, sample.txRate ?? 0), 0);
	function paths(direction: 'rxRate' | 'txRate') {
		const result: { line: string; area: string }[] = [];
		let points: [number, number][] = [];
		function flush() {
			if (points.length >= 2) {
				const line = points.map(([x, y], index) => `${index ? 'L' : 'M'}${x},${y}`).join(' ');
				result.push({ line, area: `${line} L${points.at(-1)![0]},${height} L${points[0][0]},${height} Z` });
			}
			points = [];
		}
		for (const sample of samples) {
			const value = sample[direction];
			if (value === null || !Number.isFinite(value) || value < 0) {
				flush();
				continue;
			}
			const x = last > first ? (sample.timestamp - first) / (last - first) * width : 0;
			const y = peak > 0 ? height - value / peak * height : height;
			points.push([x, y]);
		}
		flush();
		return result;
	}
	return { width, height, peak, first, last, rx: paths('rxRate'), tx: paths('txRate') };
}
