import { describe, expect, it } from 'vitest';
import { applyTranscriptionFrame, realtimeReadiness, type RealtimeCapabilities, type RealtimeModel } from '../realtimeVoice';
import { t } from '$lib/i18n/ns/chat-studio';

const input = { available: true, mode: 'native' as const, reason_code: null, pricing_available: true };
const model: RealtimeModel = { id: 17, provider_id: 2, provider_type: 'openai', provider_sort_order: 0, sort_order: 0, model_name: 'gpt-realtime-whisper', display_name: 'Transcription', model_kind: 'realtime', provider_api_key_configured: true, capabilities: { feature_gates: { audio_input: input } } };
const caps: RealtimeCapabilities = { model_id: 17, model_kind: 'realtime', realtime_kind: 'transcription', model_capabilities: model.capabilities, available_voices: [], default_voice: null, input_sample_rate_hz: 24000, output_sample_rate_hz: 0, max_duration_seconds: 300 };

describe('native realtime transcription contract', () => {
	it('requires priced native input but no voice, output gate or output PCM rate', () => expect(realtimeReadiness(model, caps)).toBeNull());
	it('does not infer transcription from a model name without native capability metadata', () => expect(realtimeReadiness(model, { ...caps, realtime_kind: undefined })).not.toBeNull());
	it.each([
		{ ...caps, realtime_kind: 'live' }, { ...caps, input_sample_rate_hz: 16000 },
		{ ...caps, output_sample_rate_hz: 24000 }, { ...caps, max_duration_seconds: 0 },
		{ ...caps, model_capabilities: { feature_gates: { audio_input: { ...input, pricing_available: false } } } },
	])('rejects unsupported/malformed/unpriced transcription metadata %#', (value) => expect(realtimeReadiness(model, value)).not.toBeNull());
	it('correlates interleaved items and replaces partials with authoritative final text', () => {
		let items = applyTranscriptionFrame([], { type: 'transcript.input.delta', item_id: 'a', delta: 'hel' });
		items = applyTranscriptionFrame(items, { type: 'transcript.input.delta', item_id: 'b', delta: 'other' });
		items = applyTranscriptionFrame(items, { type: 'transcript.input.completed', item_id: 'a', text: 'hello' });
		items = applyTranscriptionFrame(items, { type: 'transcript.input.delta', item_id: 'a', delta: 'duplicate' });
		expect(items).toEqual([{ id: 'a', text: 'hello', state: 'final' }, { id: 'b', text: 'other', state: 'partial' }]);
		items = applyTranscriptionFrame(items, { type: 'transcript.input.failed', item_id: 'b' });
		expect(items[1]).toEqual({ id: 'b', text: 'other', state: 'failed' });
	});
	it('retains an authoritative completion longer than the partial-preview window', () => {
		const text = 'x'.repeat(8192);
		const items = applyTranscriptionFrame([], { type: 'transcript.input.completed', item_id: 'long', text });
		expect(items[0]).toEqual({ id: 'long', text, state: 'final' });
	});
	it('bounds ephemeral transcript history and does not create final text for malformed events', () => {
		let items = applyTranscriptionFrame([], { type: 'transcript.input.completed', text: 'missing item' });
		expect(items).toEqual([]);
		for (let i = 0; i < 30; i++) items = applyTranscriptionFrame(items, { type: 'transcript.input.delta', item_id: String(i), delta: 'x'.repeat(5000) });
		expect(items).toHaveLength(20);
		expect(items[0].text).toHaveLength(4096);
		expect(items.every((item) => item.state === 'partial')).toBe(true);
	});
	it('uses a localized unsupported-mode explanation', () => expect(realtimeReadiness(model, { ...caps, realtime_kind: 'translation' })).toBe(t('realtimeTranscription.unsupported')));
});
