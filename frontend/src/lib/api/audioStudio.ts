import { t } from '$lib/i18n/ns/chat-studio';
import { api, ApiError, fetchWithAuth } from './client';
import { requireLumenCapability } from './lumenAccess';
import { uploadChatAttachment } from './chatAttachments';
import type { AvailableModel } from './chatTree';
import { parseAudioTranscript, type AudioTranscript } from './audioTranscript';

export type AudioKind = 'tts' | 'stt';
export type AudioFormat = 'mp3' | 'wav';
export interface AudioScope { token: string; projectId: string }
export interface AudioModel extends AvailableModel {
	model_kind: AudioKind;
	provider_api_key_configured: boolean;
}
export interface AudioCapabilities {
	model_id: number;
	model_kind: AudioKind;
	model_capabilities: AudioModel['capabilities'];
	available_voices?: string[];
	available_formats?: AudioFormat[];
	available_timestamp_granularities?: Array<'segment'>;
}
export interface SpeechRequest {
	model_id: string;
	input: string;
	voice: string;
	response_format: AudioFormat;
}
export interface TranscriptionRequest {
	model_id: string;
	input_asset_id: string;
	language?: string;
	timestamp_granularities?: Array<'segment'>;
}

export function audioReadiness(model: AudioModel | undefined, capabilities: AudioCapabilities | null, kind: AudioKind): string | null {
	if (!model) return t('audioStudioApi.selectModel');
	if (model.model_kind !== kind || !Number.isSafeInteger(model.id) || model.id < 1) return t('audioStudioApi.unsupportedRoute');
	if (!model.provider_api_key_configured) return t('audioStudioApi.providerKeyMissing');
	const feature = kind === 'tts' ? 'audio_output' : 'audio_input';
	const gate = model.capabilities?.feature_gates?.[feature];
	if (!gate || gate.available !== true || gate.mode !== 'native') return t('audioStudioApi.nativeRouteUnavailable');
	if (gate.pricing_available !== true) return t('audioStudioApi.pricingMissing');
	if (!capabilities || capabilities.model_id !== model.id || capabilities.model_kind !== kind) return t('audioStudioApi.readinessUnverified');
	const exact = capabilities.model_capabilities?.feature_gates?.[feature];
	if (!exact || exact.available !== true || exact.mode !== 'native') return t('audioStudioApi.currentRouteUnavailable');
	if (exact.pricing_available !== true) return t('audioStudioApi.currentPricingMissing');
	if (kind === 'tts' && (!capabilities.available_voices?.length || !capabilities.available_formats?.some((format) => format === 'mp3' || format === 'wav'))) return t('audioStudioApi.voiceFormatUnverified');
	return null;
}

async function checked(response: Response, fallback: 'audioStudioApi.speechFailed' | 'audioStudioApi.transcriptionFailed'): Promise<Response> {
	if (response.ok) return response;
	const payload = await response.json().catch(() => null);
	throw new ApiError(response.status, typeof payload?.detail === 'string' ? payload.detail : t(fallback, { status: response.status }));
}

export const audioStudioApi = {
	models: (kind: AudioKind, scope: AudioScope) => api.get<AudioModel[]>(`/api/v1/chat/models?model_kind=${kind}`, scope.token, scope.projectId, { refresh: true }),
	capabilities: (kind: AudioKind, id: number, scope: AudioScope) => api.get<AudioCapabilities>(`/api/v1/chat/capabilities?model_id=${id}&model_kind=${kind}`, scope.token, scope.projectId, { refresh: true }),
	async speech(request: SpeechRequest, scope: AudioScope, idempotencyKey: string, signal?: AbortSignal): Promise<Blob> {
		requireLumenCapability('lumen-audio_user', scope.token, scope.projectId);
		const response = await checked(await fetchWithAuth('/api/v1/chat/audio/speech', {
			method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
			body: JSON.stringify(request), signal
		}, scope.token, scope.projectId), 'audioStudioApi.speechFailed');
		const blob = await response.blob();
		if (!blob.size || !response.headers.get('content-type')?.toLowerCase().startsWith('audio/')) throw new Error(t('audioStudioApi.invalidSpeechResponse'));
		return blob;
	},
	upload: (file: File, scope: AudioScope, signal?: AbortSignal) => uploadChatAttachment(file, { ...scope, signal }),
	async transcribe(request: TranscriptionRequest, scope: AudioScope, intentKey: string, signal?: AbortSignal): Promise<AudioTranscript> {
		requireLumenCapability('lumen-audio_user', scope.token, scope.projectId);
		const response = await checked(await fetchWithAuth('/api/v1/chat/audio/transcriptions', {
			method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': intentKey },
			body: JSON.stringify(request), signal
		}, scope.token, scope.projectId), 'audioStudioApi.transcriptionFailed');
		const result: unknown = await response.json();
		return parseAudioTranscript(result, request.timestamp_granularities?.includes('segment') === true);
	}
};
