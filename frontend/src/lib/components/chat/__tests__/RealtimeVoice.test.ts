import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import type * as RealtimeModule from '$lib/api/realtimeVoice';
import RealtimeVoice from '../RealtimeVoice.svelte';
import { t } from '$lib/i18n/ns/chat-studio';

const calls = vi.hoisted(() => ({ models: vi.fn(), capabilities: vi.fn(), createSession: vi.fn(), connect: vi.fn() }));
vi.mock('$lib/api/realtimeVoice', async (original) => ({ ...await original<typeof RealtimeModule>(), realtimeVoiceApi: calls }));
const gate = (priced = true) => ({ feature_gates: {
	audio_input: { available: true, mode: 'native', pricing_available: priced },
	audio_output: { available: true, mode: 'native', pricing_available: priced }
} });
const model = (priced = true) => ({ id: 17, model_kind: 'realtime', model_name: 'voice', display_name: 'Voice',
	provider_api_key_configured: true, capabilities: gate(priced) });
const capability = (priced = true) => ({ model_id: 17, model_kind: 'realtime', model_capabilities: gate(priced),
	available_voices: ['alloy', 'nova'], default_voice: 'alloy', input_sample_rate_hz: 24000,
	output_sample_rate_hz: 24000, max_duration_seconds: 900 });
const user = (projectId: string) => ({ token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'owner',
	username: 'tester', projectId, projectName: projectId, availableProjects: [], roles: [], isSystemAdmin: false, federated: false });

class Socket {
	static OPEN = 1;
	static instances: Socket[] = [];
	readyState = 0;
	onmessage: ((event: MessageEvent) => void) | null = null;
	onclose: (() => void) | null = null;
	onerror: (() => void) | null = null;
	sent: string[] = [];
	closed = false;
	constructor() { Socket.instances.push(this); }
	send(value: string) { this.sent.push(value); }
	close() { this.readyState = 3; this.closed = true; }
	open() { this.readyState = 1; }
	message(value: Record<string, unknown>) { this.onmessage?.({ data: JSON.stringify(value) } as MessageEvent); }
}

class Capture {
	static current: Capture | null = null;
	port: { onmessage: ((event: MessageEvent<ArrayBuffer>) => void) | null } = { onmessage: null };
	disconnect = vi.fn();
	connect = vi.fn();
	constructor() { Capture.current = this; }
}

class Context {
	static current: Context | null = null;
	currentTime = 1;
	audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) };
	close = vi.fn().mockResolvedValue(undefined);
	resume = vi.fn().mockResolvedValue(undefined);
	microphone = { connect: vi.fn(), disconnect: vi.fn() };
	source = { connect: vi.fn(), disconnect: vi.fn(), start: vi.fn(), stop: vi.fn(), onended: null as (() => void) | null, buffer: null as unknown };
	buffer = { duration: 0.0000833, getChannelData: vi.fn(() => new Float32Array(2)) };
	destination = {};
	constructor() { Context.current = this; }
	createMediaStreamSource() { return this.microphone; }
	createBuffer(_channels: number, frames: number, rate: number) { expect([frames, rate]).toEqual([2, 24000]); return this.buffer; }
	createBufferSource() { return this.source; }
}

beforeEach(() => {
	vi.clearAllMocks();
	Socket.instances = [];
	Capture.current = null;
	Context.current = null;
	auth.set(user('project-1'));
	calls.models.mockResolvedValue([model()]);
	calls.capabilities.mockResolvedValue(capability());
	calls.createSession.mockResolvedValue({ session_id: 'session-1', status: 'ready', provider_type: 'openai', ticket: 'opaque', websocket_path: '/api/v1/chat/realtime/ws' });
	calls.connect.mockImplementation(() => new Socket());
	vi.stubGlobal('WebSocket', Socket);
	vi.stubGlobal('AudioWorkletNode', Capture);
	vi.stubGlobal('AudioContext', Context);
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('Realtime Voice', () => {
	it('shows a labeled connecting status and removes it when the attempt is canceled', async () => {
		const microphone = Promise.withResolvers<MediaStream>();
		const trackStop = vi.fn();
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockReturnValue(microphone.promise) } });
		render(RealtimeVoice);
		await screen.findByText('음성 입력·출력 경로와 가격이 준비되었습니다.');
		await fireEvent.click(screen.getByRole('button', { name: '음성 세션 시작' }));
		const connecting = t('realtimeVoice.connecting');
		await waitFor(() => expect(screen.queryAllByRole('status').some((item) => item.textContent?.includes(connecting))).toBe(true));
		expect(screen.getByRole('button', { name: connecting }).hasAttribute('disabled')).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '세션 종료' }));
		expect(screen.queryAllByRole('status').some((item) => item.textContent?.includes(connecting))).toBe(false);
		microphone.resolve({ getTracks: () => [{ stop: trackStop }] } as unknown as MediaStream);
		await waitFor(() => expect(trackStop).toHaveBeenCalled());
		expect(calls.createSession).not.toHaveBeenCalled();
	});

	it('does not request microphone permission for unavailable or unpriced routes', async () => {
		calls.models.mockResolvedValue([model(false)]);
		calls.capabilities.mockResolvedValue(capability(false));
		const media = vi.fn();
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: media } });
		render(RealtimeVoice);
		await screen.findByText('실시간 오디오 가격이 설정되지 않았습니다.');
		expect(screen.getByRole('button', { name: '음성 세션 시작' }).hasAttribute('disabled')).toBe(true);
		expect(media).not.toHaveBeenCalled();
	});

	it('streams PCM only after explicit permission, interrupts playback, clears both transcripts and resources on project change', async () => {
		const stop = vi.fn();
		const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] });
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia } });
		render(RealtimeVoice);
		await screen.findByText('음성 입력·출력 경로와 가격이 준비되었습니다.');
		expect(getUserMedia).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '음성 세션 시작' }));
		await waitFor(() => expect(calls.createSession).toHaveBeenCalledWith(17, 'alloy',
			{ token: 'token', projectId: 'project-1' }, expect.any(String), expect.any(AbortSignal)));
		const socket = Socket.instances[0];
		socket.open();
		socket.message({ type: 'session.ready', session_id: 'session-1', input_sample_rate_hz: 24000,
			output_sample_rate_hz: 24000 });
		await screen.findByText('실시간 연결 중 · 마이크 켜짐');
		const pcm = new Int16Array([-32768, 32767]);
		Capture.current?.port.onmessage?.({ data: pcm.buffer } as MessageEvent<ArrayBuffer>);
		const sent = JSON.parse(socket.sent[0]);
		expect(sent.type).toBe('audio.input.append');
		expect(Array.from(atob(sent.audio), (char) => char.charCodeAt(0))).toEqual([0, 128, 255, 127]);
		socket.message({ type: 'transcript.input.delta', delta: 'hello' });
		socket.message({ type: 'transcript.output.delta', delta: 'world' });
		await screen.findByText('hello');
		await screen.findByText('world');
		socket.message({ type: 'audio.output.delta', delta: sent.audio, sample_rate_hz: 24000 });
		expect(Context.current?.source.start).toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '응답 끊기' }));
		expect(Context.current?.source.stop).toHaveBeenCalled();
		expect(socket.sent.map((frame) => JSON.parse(frame).type)).toContain('response.cancel');
		await fireEvent.click(screen.getByRole('button', { name: '마이크 끄기' }));
		Capture.current?.port.onmessage?.({ data: pcm.buffer } as MessageEvent<ArrayBuffer>);
		expect(socket.sent.filter((frame) => JSON.parse(frame).type === 'audio.input.append')).toHaveLength(1);
		auth.set(user('project-2'));
		await waitFor(() => expect(stop).toHaveBeenCalled());
		expect(Context.current?.close).toHaveBeenCalled();
		expect(socket.closed).toBe(true);
		expect(screen.queryByText('hello')).toBeNull();
		expect(screen.queryByText('world')).toBeNull();
	});

	it('closes Gemini Live session rather than sending an unsupported response cancel', async () => {
		const trackStop = vi.fn();
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: {
			getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: trackStop }] }) } });
		calls.createSession.mockResolvedValue({ session_id: 'session-1', status: 'ready', provider_type: 'gemini',
			ticket: 'opaque', websocket_path: '/api/v1/chat/realtime/ws' });
		render(RealtimeVoice);
		await screen.findByText('음성 입력·출력 경로와 가격이 준비되었습니다.');
		await fireEvent.click(screen.getByRole('button', { name: '음성 세션 시작' }));
		await waitFor(() => expect(Socket.instances).toHaveLength(1));
		const socket = Socket.instances[0];
		socket.open();
		socket.message({ type: 'session.ready', input_sample_rate_hz: 16000, output_sample_rate_hz: 24000 });
		await screen.findByText('실시간 연결 중 · 마이크 켜짐');
		await fireEvent.click(screen.getByRole('button', { name: '응답 끊기 · 세션 종료' }));
		expect(socket.sent.map((frame) => JSON.parse(frame).type)).toEqual(['session.close']);
		expect(socket.closed).toBe(true);
		expect(trackStop).toHaveBeenCalled();
	});

	it('retries uncertain session admission with the same intent key', async () => {
		const trackStop = vi.fn();
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: {
			getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: trackStop }] }) } });
		calls.createSession.mockRejectedValueOnce(new Error('network timeout'));
		render(RealtimeVoice);
		await screen.findByText('음성 입력·출력 경로와 가격이 준비되었습니다.');
		await fireEvent.click(screen.getByRole('button', { name: '음성 세션 시작' }));
		await screen.findByText('실시간 음성 세션을 시작하지 못했습니다.');
		expect(trackStop).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: '음성 세션 시작' }));
		await waitFor(() => expect(calls.createSession).toHaveBeenCalledTimes(2));
		expect(calls.createSession.mock.calls[1][3]).toBe(calls.createSession.mock.calls[0][3]);
	});

	it('reports denied microphone access and releases connecting state without creating a session', async () => {
		const getUserMedia = vi.fn().mockRejectedValue(new DOMException('denied', 'NotAllowedError'));
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia } });
		render(RealtimeVoice);
		await screen.findByText('음성 입력·출력 경로와 가격이 준비되었습니다.');
		await fireEvent.click(screen.getByRole('button', { name: '음성 세션 시작' }));
		await screen.findByText('마이크 권한이 거부되었습니다.');
		expect(calls.createSession).not.toHaveBeenCalled();
		expect(screen.getByRole('button', { name: '음성 세션 시작' }).hasAttribute('disabled')).toBe(false);
	});
});
