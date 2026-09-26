import { describe, expect, it } from 'vitest';
import { trafficAreaGeometry } from '../trafficArea';

describe('traffic area geometry', () => {
	it('uses elapsed report time and one zero-based axis for both directions', () => {
		const graph = trafficAreaGeometry([
			{ timestamp: 0, rxRate: 0, txRate: 20 },
			{ timestamp: 10, rxRate: 10, txRate: 10 },
			{ timestamp: 30, rxRate: 20, txRate: 0 },
		]);
		expect(graph.peak).toBe(20);
		expect(graph.rx[0].line).toBe('M0,64 L100,32 L300,0');
		expect(graph.tx[0].line).toBe('M0,0 L100,32 L300,64');
	});

	it('leaves missing/reset intervals disconnected rather than drawing synthetic traffic', () => {
		const graph = trafficAreaGeometry([
			{ timestamp: 0, rxRate: 10, txRate: null },
			{ timestamp: 10, rxRate: 20, txRate: null },
			{ timestamp: 20, rxRate: null, txRate: null },
			{ timestamp: 30, rxRate: 20, txRate: 10 },
			{ timestamp: 40, rxRate: 10, txRate: null },
		]);
		expect(graph.rx.map((path) => path.line)).toEqual(['M0,32 L75,0', 'M225,0 L300,32']);
		expect(graph.tx).toEqual([]);
	});

	it('does not invent a wave from zero traffic or a single rate', () => {
		expect(trafficAreaGeometry([{ timestamp: 0, rxRate: 8, txRate: null }]).rx).toEqual([]);
		const graph = trafficAreaGeometry([
			{ timestamp: 0, rxRate: 0, txRate: 0 },
			{ timestamp: 10, rxRate: 0, txRate: 0 },
		]);
		expect(graph.rx[0].line).toBe('M0,64 L300,64');
		expect(graph.peak).toBe(0);
	});
});
