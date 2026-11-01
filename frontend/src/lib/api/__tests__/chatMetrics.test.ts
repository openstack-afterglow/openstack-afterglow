// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { computeMetrics, estimateTokens, formatMetrics, observeTtft } from '../chatMetrics';
import type { ChatRunEvent } from '../chatContracts';

describe('estimateTokens', () => {
	it('4 chars ≈ 1 token 근사', () => {
		expect(estimateTokens(0)).toBe(0);
		expect(estimateTokens(4)).toBe(1);
		expect(estimateTokens(400)).toBe(100);
	});
	it('0 초과면 최소 1', () => {
		expect(estimateTokens(1)).toBe(1);
	});
});

describe('computeMetrics', () => {
	it('firstToken 이 없으면 null', () => {
		expect(computeMetrics(100, null, 5000, false)).toBeNull();
	});
	it('tok/s = tokens / elapsedSeconds', () => {
		const m = computeMetrics(340, 1000, 3000, false);
		expect(m).not.toBeNull();
		expect(m!.seconds).toBeCloseTo(2.0);
		expect(m!.tokPerSec).toBeCloseTo(170);
		expect(m!.approximate).toBe(false);
	});
	it('elapsed 0 이면 0 나눗셈 없이 tokPerSec=0', () => {
		const m = computeMetrics(100, 5000, 5000, true);
		expect(m!.tokPerSec).toBe(0);
	});
	it('tokens 0 이면 tokPerSec=0', () => {
		const m = computeMetrics(0, 1000, 3000, true);
		expect(m!.tokPerSec).toBe(0);
	});
	it('retains observed TTFT without inventing tokens or throughput for completed-only text', () => {
		const m = computeMetrics(0, null, 8000, false, 2.75);
		expect(m).toEqual({ tokens: null, seconds: null, tokPerSec: null, approximate: false, ttftSeconds: 2.75 });
		expect(formatMetrics(m)).toBe('');
	});
	it('keeps throughput measured from the first delta, independently of submission time', () => {
		const m = computeMetrics(100, 4000, 6000, false, 3);
		expect(m).toMatchObject({ seconds: 2, tokPerSec: 50, ttftSeconds: 3 });
	});
});

describe('formatMetrics', () => {
	it('null 이면 빈 문자열', () => {
		expect(formatMetrics(null)).toBe('');
	});
	it('0 항목은 생략', () => {
		expect(formatMetrics({ tokens: 0, seconds: 0, tokPerSec: 0, approximate: false })).toBe('');
	});
});

const baseEvent = { event_id: 'run:1', run_id: 'run', seq: 1, created_at: '2026-10-30T00:00:00Z' };
function delta(text: string, partType: 'text' | 'reasoning' = 'text', messageId = 'answer'): ChatRunEvent {
	return { ...baseEvent, type: 'part.delta', payload: { message_id: messageId, part_index: 0, part_type: partType, delta: text } };
}
function completed(text: string, partType: 'text' | 'reasoning' = 'text'): ChatRunEvent {
	return {
		...baseEvent,
		type: 'part.completed',
		payload: { message_id: 'answer', part_index: 0, part: partType === 'text' ? { type: 'text', text } : { type: 'reasoning', text, visibility: 'user' } }
	};
}

describe('observeTtft', () => {
	it('ignores reasoning, tools, status, non-current messages and empty fragments', () => {
		const ignored: ChatRunEvent[] = [
			delta('thinking', 'reasoning'), completed('thinking', 'reasoning'),
			delta('old answer', 'text', 'previous'),
			{ ...baseEvent, type: 'run.stage.changed', payload: { stage: 'model_response', tool_name: null } },
			{ ...baseEvent, type: 'tool.call.completed', payload: { call_id: 'call', name: 'tool', content: [{ type: 'text', text: 'result' }], status: 'completed', error_code: null, source: 'builtin', category: 'read' } },
			// Defensive boundary only: strict wire parsing already rejects empty text.
			delta(''), completed('')
		];
		for (const evt of ignored) expect(observeTtft(null, 1000, evt, 'answer', 3000)).toBeNull();
		expect(observeTtft(null, 1000, delta('tool text'), null, 3000)).toBeNull();
	});
	it('observes completed-only answer text and accepts a monotonic zero as a real observation', () => {
		expect(observeTtft(null, 1000, completed('answer'), 'answer', 3750)).toBe(2.75);
		expect(observeTtft(null, 1000, delta('answer'), 'answer', 1000)).toBe(0);
	});
	it('freezes across more text, completed text, replay and later message rounds', () => {
		const first = observeTtft(null, 1000, delta('first'), 'answer', 3000);
		expect(first).toBe(2);
		for (const evt of [delta('more'), completed('final'), delta('next', 'text', 'next-answer')]) {
			expect(observeTtft(first, 1000, evt, 'next-answer', 9000)).toBe(2);
		}
	});
	it('starts retries afresh while resumed runs and no-answer terminal events stay unavailable', () => {
		const evt = delta('answer');
		expect(observeTtft(null, 1000, evt, 'answer', 5000)).toBe(4);
		expect(observeTtft(null, 4500, evt, 'answer', 5000)).toBe(0.5);
		expect(observeTtft(null, null, evt, 'answer', 5000)).toBeNull();
		const failed: ChatRunEvent = { ...baseEvent, type: 'run.failed', payload: { status: 'failed', message_id: null, error_code: 'failed', safe_message: 'Failed' } };
		expect(observeTtft(null, 1000, failed, 'answer', 5000)).toBeNull();
		expect(observeTtft(2, 1000, failed, 'answer', 5000)).toBe(2);
	});
});
