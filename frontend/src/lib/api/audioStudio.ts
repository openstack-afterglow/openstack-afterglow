import { api, ApiError, fetchWithAuth } from './client';
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
	if (!model) return '오디오 모델을 선택하세요.';
	if (model.model_kind !== kind || !Number.isSafeInteger(model.id) || model.id < 1) return '선택한 모델은 이 오디오 경로를 지원하지 않습니다.';
	if (!model.provider_api_key_configured) return '제공자 API 키가 구성되지 않았습니다.';
	const feature = kind === 'tts' ? 'audio_output' : 'audio_input';
	const gate = model.capabilities?.feature_gates?.[feature];
	if (!gate || gate.available !== true || gate.mode !== 'native') return '모델의 기본 오디오 경로를 사용할 수 없습니다.';
	if (gate.pricing_available !== true) return '오디오 가격이 설정되지 않았습니다.';
	if (!capabilities || capabilities.model_id !== model.id || capabilities.model_kind !== kind) return '모델의 사용 가능 상태를 확인하지 못했습니다.';
	const exact = capabilities.model_capabilities?.feature_gates?.[feature];
	if (!exact || exact.available !== true || exact.mode !== 'native') return '현재 오디오 경로를 사용할 수 없습니다.';
	if (exact.pricing_available !== true) return '현재 오디오 가격이 설정되지 않았습니다.';
	if (kind === 'tts' && (!capabilities.available_voices?.length || !capabilities.available_formats?.some((format) => format === 'mp3' || format === 'wav'))) return '이 모델의 지원 목소리와 음성 형식을 확인할 수 없습니다.';
	return null;
}

async function checked(response: Response, fallback: string): Promise<Response> {
	if (response.ok) return response;
	const payload = await response.json().catch(() => null);
	throw new ApiError(response.status, typeof payload?.detail === 'string' ? payload.detail : `${fallback} (${response.status})`);
}

export const audioStudioApi = {
	models: (kind: AudioKind, scope: AudioScope) => api.get<AudioModel[]>(`/api/v1/chat/models?model_kind=${kind}`, scope.token, scope.projectId, { refresh: true }),
	capabilities: (kind: AudioKind, id: number, scope: AudioScope) => api.get<AudioCapabilities>(`/api/v1/chat/capabilities?model_id=${id}&model_kind=${kind}`, scope.token, scope.projectId, { refresh: true }),
	async speech(request: SpeechRequest, scope: AudioScope, idempotencyKey: string, signal?: AbortSignal): Promise<Blob> {
		const response = await checked(await fetchWithAuth('/api/v1/chat/audio/speech', {
			method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
			body: JSON.stringify(request), signal
		}, scope.token, scope.projectId), '음성 생성 실패');
		const blob = await response.blob();
		if (!blob.size || !response.headers.get('content-type')?.toLowerCase().startsWith('audio/')) throw new Error('음성 응답이 유효하지 않습니다.');
		return blob;
	},
	upload: (file: File, scope: AudioScope, signal?: AbortSignal) => uploadChatAttachment(file, { ...scope, signal }),
	async transcribe(request: TranscriptionRequest, scope: AudioScope, intentKey: string, signal?: AbortSignal): Promise<AudioTranscript> {
		const response = await checked(await fetchWithAuth('/api/v1/chat/audio/transcriptions', {
			method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': intentKey },
			body: JSON.stringify(request), signal
		}, scope.token, scope.projectId), '음성 인식 실패');
		const result: unknown = await response.json();
		return parseAudioTranscript(result, request.timestamp_granularities?.includes('segment') === true);
	}
};
