// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { formatTranscriptTime, parseAudioTranscript, transcriptSrt, transcriptText } from '../audioTranscript';

const timed = {
	text: '첫 문장.\n다음 문장.',
	segments: [{ start: 1.2, end: 3.8, text: ' 첫 문장. ' }, { start: 4.125, end: 6.5, text: '다음 문장.' }]
};

describe('audio transcript timing', () => {
	it('keeps real time ranges and strips provider-only metadata', () => {
		expect(parseAudioTranscript({ ...timed, segments: timed.segments.map((segment) => ({ ...segment, tokens: [1, 2], avg_logprob: -0.2 })) }, true)).toEqual(timed);
	});

	it('keeps plain and genuinely silent transcription distinct from missing requested timing', () => {
		expect(parseAudioTranscript({ text: '인식된 문장' })).toEqual({ text: '인식된 문장', segments: [] });
		expect(parseAudioTranscript({ text: '', segments: [] }, true)).toEqual({ text: '', segments: [] });
		expect(() => parseAudioTranscript({ text: '인식된 문장' }, true)).toThrow();
		expect(() => parseAudioTranscript({ text: '인식된 문장', segments: [] }, true)).toThrow();
	});

	it.each([
		{ start: -1, end: 1, text: '음성' },
		{ start: true, end: 1, text: '음성' },
		{ start: '0', end: 1, text: '음성' },
		{ start: Number.NaN, end: 1, text: '음성' },
		{ start: 0, end: Number.POSITIVE_INFINITY, text: '음성' },
		{ start: 2, end: 1, text: '음성' },
		{ start: 0, end: 1801, text: '음성' },
		{ start: 0, end: 1, text: null }
	])('rejects malformed timing rather than inventing alignment: %j', (segment) => {
		expect(() => parseAudioTranscript({ text: '음성', segments: [segment] }, true)).toThrow();
	});

	it('rejects overlapping or reordered segments and an unbounded response', () => {
		expect(() => parseAudioTranscript({ text: '음성', segments: [{ start: 2, end: 4, text: '첫 문장' }, { start: 3, end: 5, text: '다음 문장' }] })).toThrow();
		expect(() => parseAudioTranscript({ text: '음성', segments: Array.from({ length: 4097 }, () => ({ start: 0, end: 0, text: '' })) })).toThrow();
		expect(() => parseAudioTranscript({ text: '음성', segments: null })).toThrow();
		expect(() => parseAudioTranscript({ text: 'x'.repeat(65537) })).toThrow();
	});

	it.each([[0, '00:00:00.000'], [1.234, '00:00:01.234'], [59.9996, '00:01:00.000'], [1799.9996, '00:30:00.000']])('formats %s seconds without broken millisecond carry', (seconds, formatted) => {
		expect(formatTranscriptTime(seconds)).toBe(formatted);
	});

	it('exports readable timed TXT and valid numbered SRT from the same provider ranges', () => {
		expect(transcriptText(timed)).toBe('[00:00:01.200 → 00:00:03.800]\n첫 문장.\n\n[00:00:04.125 → 00:00:06.500]\n다음 문장.\n');
		expect(transcriptSrt(timed)).toBe('1\n00:00:01,200 --> 00:00:03,800\n첫 문장.\n\n2\n00:00:04,125 --> 00:00:06,500\n다음 문장.\n');
	});

	it('keeps text-only download useful but refuses a fabricated SRT', () => {
		const plain = parseAudioTranscript({ text: '시각 없는 원문\n다음 문장' });
		expect(transcriptText(plain)).toBe('시각 없는 원문\n다음 문장');
		expect(() => transcriptSrt(plain)).toThrow();
	});

	it('normalizes paragraph breaks inside a subtitle without creating extra cues', () => {
		expect(transcriptSrt({ text: '두 줄', segments: [{ start: 0, end: 1, text: '첫 줄\r\n\r\n다음 줄' }] })).toBe('1\n00:00:00,000 --> 00:00:01,000\n첫 줄\n다음 줄\n');
	});
});
