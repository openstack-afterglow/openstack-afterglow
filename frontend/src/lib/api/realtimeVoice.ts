import { api, ApiError, fetchWithAuth, getWebSocketUrl } from './client';
import type { AvailableModel } from './chatTree';

export interface RealtimeScope { token: string; projectId: string }
export interface RealtimeModel extends AvailableModel {
	model_kind: 'realtime';
	provider_api_key_configured: boolean;
}
export interface RealtimeCapabilities {
	model_id: number;
	model_kind: 'realtime';
	model_capabilities: RealtimeModel['capabilities'];
	available_voices: string[];
	default_voice: string | null;
	input_sample_rate_hz: number;
	output_sample_rate_hz: number;
	max_duration_seconds: number;
}
export interface RealtimeSession {
	session_id: string;
	status: 'ready';
	model_name: string;
	provider_type: string;
	expires_at: string;
	ticket: string;
	websocket_path: string;
}

export function realtimeReadiness(model: RealtimeModel | undefined, current: RealtimeCapabilities | null): string | null {
	if (!model) return '실시간 음성 모델을 선택하세요.';
	if (model.model_kind !== 'realtime' || !Number.isSafeInteger(model.id) || model.id <= 0) return '지원하지 않는 모델입니다.';
	if (!model.provider_api_key_configured) return '제공자 API 키가 구성되지 않았습니다.';
	if (!current || current.model_kind !== 'realtime' || current.model_id !== model.id) return '현재 모델 상태를 확인할 수 없습니다.';
	for (const gates of [model.capabilities?.feature_gates, current.model_capabilities?.feature_gates]) {
		for (const name of ['audio_input', 'audio_output'] as const) {
			const gate = gates?.[name];
			if (!gate || gate.available !== true || gate.mode !== 'native') return '실시간 오디오 경로를 사용할 수 없습니다.';
			if (gate.pricing_available !== true) return '실시간 오디오 가격이 설정되지 않았습니다.';
		}
	}
	if (!current.available_voices?.length || !current.default_voice || !current.available_voices.includes(current.default_voice) ||
		![16000, 24000].includes(current.input_sample_rate_hz) || current.output_sample_rate_hz !== 24000 || current.max_duration_seconds < 10) {
		return '이 모델의 음성 스트림 형식을 확인할 수 없습니다.';
	}
	return null;
}

export const realtimeVoiceApi = {
	models: (scope: RealtimeScope) => api.get<RealtimeModel[]>('/api/v1/chat/models?model_kind=realtime', scope.token, scope.projectId, { refresh: true }),
	capabilities: (id: number, scope: RealtimeScope) => api.get<RealtimeCapabilities>(`/api/v1/chat/capabilities?model_id=${id}&model_kind=realtime`, scope.token, scope.projectId, { refresh: true }),
	async createSession(modelId: number, voice: string, scope: RealtimeScope, key: string, signal: AbortSignal): Promise<RealtimeSession> {
		const response = await fetchWithAuth('/api/v1/chat/realtime/sessions', {
			method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
			body: JSON.stringify({ model_id: String(modelId), voice, max_duration_seconds: 300 }), signal
		}, scope.token, scope.projectId);
		if (!response.ok) {
			const payload = await response.json().catch(() => null);
			throw new ApiError(response.status, typeof payload?.detail === 'string' ? payload.detail : '음성 세션을 시작하지 못했습니다.');
		}
		const session: RealtimeSession = await response.json();
		if (session.status !== 'ready' || !session.ticket || session.websocket_path !== '/api/v1/chat/realtime/ws') throw new Error('잘못된 음성 세션 응답입니다.');
		return session;
	},
	connect(session: RealtimeSession): WebSocket {
		const url = new URL(getWebSocketUrl(session.websocket_path));
		url.searchParams.set('ticket', session.ticket);
		return new WebSocket(url.toString());
	}
};

export function pcm16Base64(samples: Int16Array): string {
	const bytes = new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength);
	let chars = '';
	for (let i = 0; i < bytes.length; i++) chars += String.fromCharCode(bytes[i]);
	return btoa(chars);
}

export function decodePcm16(value: string): Float32Array {
	const binary = atob(value);
	if (!binary || binary.length % 2 || binary.length > 64 * 1024) throw new Error('유효하지 않은 오디오 프레임입니다.');
	const samples = new Float32Array(binary.length / 2);
	for (let i = 0; i < samples.length; i++) {
		const low = binary.charCodeAt(i * 2);
		const high = binary.charCodeAt(i * 2 + 1);
		const word = (high << 8) | low;
		samples[i] = (word & 0x8000 ? word - 0x10000 : word) / 32768;
	}
	return samples;
}
