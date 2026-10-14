import { describe, expect, it } from 'vitest';
import { trafficAreaSeries } from '../trafficArea';

describe('traffic observations', () => {
	it('keeps missing/reset intervals and isolated measurements out of connected traffic', () => {
		const graph = trafficAreaSeries([
			{ timestamp: 0, rxRate: 10, txRate: null },
			{ timestamp: 10, rxRate: 20, txRate: null },
			{ timestamp: 20, rxRate: null, txRate: null },
			{ timestamp: 30, rxRate: 20, txRate: 10 },
			{ timestamp: 40, rxRate: 10, txRate: null },
		]);
		expect(graph.data.map(row => row.rxRate)).toEqual([10, 20, null, 20, 10]);
		expect(graph.data.map(row => row.txRate)).toEqual([null, null, null, null, null]);
		expect(graph.hasGraph).toBe(true);
	});

	it('distinguishes a measured zero interval from an unestablished rate', () => {
		expect(trafficAreaSeries([{ timestamp: 0, rxRate: 8, txRate: null }]).hasGraph).toBe(false);
		const graph = trafficAreaSeries([
			{ timestamp: 0, rxRate: 0, txRate: 0 },
			{ timestamp: 10, rxRate: 0, txRate: 0 },
		]);
		expect(graph.hasGraph).toBe(true);
		expect(graph.data.map(row => row.rxRate)).toEqual([0, 0]);
		expect(graph.peak).toBe(0);
	});

	it('rejects invalid rates without creating a zero measurement', () => {
		const graph = trafficAreaSeries([
			{ timestamp: 0, rxRate: 5, txRate: -1 },
			{ timestamp: 10, rxRate: Number.NaN, txRate: 3 },
			{ timestamp: 20, rxRate: 5, txRate: Number.POSITIVE_INFINITY },
		]);
		expect(graph.hasGraph).toBe(false);
		expect(graph.data.every(row => row.rxRate === null && row.txRate === null)).toBe(true);
	});
});
