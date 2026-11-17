import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { describe, expect, it } from 'vitest';

interface CaptureProcessor {
	port: { onmessage: (event: { data: { type: string; id: number } }) => void };
	process(input: Float32Array[][]): boolean;
}

describe('PCM capture turn boundary', () => {
	it('flushes the remaining PCM before its acknowledgment and never replays it', () => {
		const sent: unknown[] = [];
		let Processor: new(options: { processorOptions: { targetRate: number } }) => CaptureProcessor;
		class Base { port = { postMessage: (message: unknown) => sent.push(message), onmessage: null }; }
		runInNewContext(readFileSync('static/audio/pcm16-capture.js', 'utf8'), {
			AudioWorkletProcessor: Base, sampleRate: 24000,
			registerProcessor: (_name: string, value: typeof Processor) => { Processor = value; }
		});
		const processor = new Processor!({ processorOptions: { targetRate: 24000 } });
		processor.process([[new Float32Array([0.5, -0.5])]]);
		expect(sent).toEqual([]);
		processor.port.onmessage({ data: { type: 'flush', id: 1 } });
		expect(Array.from(new Int16Array(sent[0] as ArrayBuffer))).toEqual([16384, -16384]);
		expect(sent[1]).toEqual({ type: 'flushed', id: 1 });
		processor.port.onmessage({ data: { type: 'flush', id: 2 } });
		expect(sent).toHaveLength(3);
		expect(sent[2]).toEqual({ type: 'flushed', id: 2 });
	});
});
