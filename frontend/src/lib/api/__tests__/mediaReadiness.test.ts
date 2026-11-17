import { describe, expect, it } from 'vitest';
import { mediaGateReadiness } from '../mediaReadiness';
import { imageModelReadiness, type ImageModel } from '../imageStudio';
import { audioReadiness, type AudioModel, type AudioCapabilities } from '../audioStudio';
import { t } from '$lib/i18n/ns/chat-studio';

const gate = { available: true, mode: 'native' as const, reason_code: null, pricing_available: true };
const base = { provider_id: 1, provider_type: 'openai', provider_sort_order: 0, sort_order: 0, model_name: 'fixture', display_name: 'Fixture', provider_api_key_configured: true };
describe('media readiness reasons', () => {
	it('does not label a verified route as unverified', () => expect(mediaGateReadiness(gate)).toBeNull());
	it('distinguishes missing price from missing pipeline', () => {
		expect(mediaGateReadiness({ ...gate, pricing_available: false })).toBe(t('mediaReadiness.price'));
		expect(mediaGateReadiness({ ...gate, available: false, mode: 'none', reason_code: 'asset_pipeline_unavailable' })).toBe(t('mediaReadiness.assets'));
	});
	it('does not claim an unsupported model from a conflated route gate', () => {
		expect(mediaGateReadiness({ ...gate, available: false, reason_code: 'route_unavailable' })).toBe(t('mediaReadiness.route'));
		expect(mediaGateReadiness(undefined)).toBe(t('mediaReadiness.unverified'));
	});
	it.each(['asset_pipeline_unavailable', 'route_unavailable'])('uses the same %s reason in image and audio studios', (reason_code) => {
		const blocked = { ...gate, available: false, mode: 'none' as const, reason_code };
		const image: ImageModel = { ...base, id: 1, capabilities: { feature_gates: { image_output: blocked } } };
		const audio: AudioModel = { ...base, id: 2, model_kind: 'tts', capabilities: { feature_gates: { audio_output: blocked } } };
		expect(imageModelReadiness(image)).toBe(mediaGateReadiness(blocked));
		expect(audioReadiness(audio, null, 'tts')).toBe(mediaGateReadiness(blocked));
	});
	it('also checks the exact audio capability response', () => {
		const audio: AudioModel = { ...base, id: 2, model_kind: 'tts', capabilities: { feature_gates: { audio_output: gate } } };
		const exact: AudioCapabilities = { model_id: 2, model_kind: 'tts', model_capabilities: { feature_gates: { audio_output: { ...gate, available: false, reason_code: 'asset_pipeline_unavailable' } } } };
		expect(audioReadiness(audio, exact, 'tts')).toBe(t('mediaReadiness.assets'));
	});
});
