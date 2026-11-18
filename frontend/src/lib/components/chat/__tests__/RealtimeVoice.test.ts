import { grantLumen, pendingLumen, refreshLumenAuth, setVerifiedLumenActor } from './lumenPermissionFixture';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { authReady, projectSwitching } from '$lib/stores/auth';
import type * as RealtimeModule from '$lib/api/realtimeVoice';
import type * as ClientModule from '$lib/api/client';
import RealtimeVoice from '../RealtimeVoice.svelte';
import { t } from '$lib/i18n/ns/chat-studio';
import { t as chatT } from '$lib/i18n/ns/chat-panel';
import * as experience from '$lib/utils/experience';

const calls = vi.hoisted(() => ({ models: vi.fn(), capabilities: vi.fn(), createSession: vi.fn(), connect: vi.fn(), fetch: vi.fn() }));
vi.mock('$lib/api/realtimeVoice', async (original) => ({ ...await original<typeof RealtimeModule>(), realtimeVoiceApi: calls }));
vi.mock('$lib/api/client', async (original) => ({ ...await original<typeof ClientModule>(), fetchWithAuth: calls.fetch }));
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
	username: 'tester', projectId, projectName: projectId, availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', identityDomainId: 'domain-1', identityDomainName: 'Domain', isDomainManager: false });

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
	port: { onmessage: ((event: MessageEvent<ArrayBuffer | { type: string; id: number }>) => void) | null; postMessage: (message: { type: string; id: number }) => void } = {
		onmessage: null,
		postMessage: (message) => queueMicrotask(() => this.port.onmessage?.({ data: { type: 'flushed', id: message.id } } as MessageEvent))
	};
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
	setVerifiedLumenActor(user('project-1'));
	calls.models.mockResolvedValue([model()]);
	calls.capabilities.mockResolvedValue(capability());
	calls.createSession.mockResolvedValue({ session_id: 'session-1', status: 'ready', provider_type: 'openai', ticket: 'opaque', websocket_path: '/api/v1/chat/realtime/ws' });
	calls.connect.mockImplementation(() => new Socket());
	vi.stubGlobal('WebSocket', Socket);
	vi.stubGlobal('AudioWorkletNode', Capture);
	vi.stubGlobal('AudioContext', Context);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('Realtime Voice', () => {
	it('admits the exact same-name model row from the selected provider', async () => {
		const track = { stop: vi.fn(), enabled: true };
		const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [track] });
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia } });
		calls.models.mockResolvedValue([{ ...model(), provider_id: 1, provider: 'OpenAI' }, { ...model(), id: 27, provider_id: 2, provider: 'Second OpenAI account' }]);
		calls.capabilities.mockImplementation(async (id: number) => ({ ...capability(), model_id: id }));
		calls.fetch.mockResolvedValueOnce(Response.json({ status: 'ready', provider_type: 'openai', ticket: 'opaque', websocket_path: '/api/v1/chat/realtime/ws' }));
		const actual = await vi.importActual<typeof RealtimeModule>('$lib/api/realtimeVoice');
		calls.createSession.mockImplementationOnce(actual.realtimeVoiceApi.createSession);

		render(RealtimeVoice);
		await screen.findByText(t('realtimeVoice.ready'));
		const start = screen.getByRole('button', { name: t('realtimeVoice.startSession') });
		const select = screen.getByRole('combobox', { name: t('realtimeVoice.model') });
		await fireEvent.change(screen.getByRole('combobox', { name: t('modelPicker.providers') }), { target: { value: '2' } });
		expect(select).toHaveProperty('value', '');
		expect(start).toHaveProperty('disabled', true);
		await fireEvent.change(select, { target: { value: '27' } });
		await screen.findByText(t('realtimeVoice.ready'));
		await fireEvent.click(start);

		await waitFor(() => expect(calls.fetch).toHaveBeenCalledOnce());
		const [path, request] = calls.fetch.mock.calls[0];
		expect(path).toBe('/api/v1/chat/realtime/sessions');
		expect(JSON.parse(request.body)).toEqual({ model_id: '27', model_row_id: 27, voice: 'alloy', max_duration_seconds: 300 });
	});

	it.each([
		['realtime_hold_limit', 'realtimeVoice.quotaInsufficient'],
		['invalid_function_call_id', 'realtimeVoice.providerFailed'],
		['upstream_error', 'realtimeVoice.providerFailed']
	] as const)('shows %s without losing the session before a socket close', async (code, message) => {
		const track = { stop: vi.fn(), enabled: true };
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
		render(RealtimeVoice);
		await screen.findByText(t('realtimeVoice.ready'));
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.startSession') }));
		await waitFor(() => expect(Socket.instances).toHaveLength(1));
		const socket = Socket.instances[0];
		socket.open();
		socket.message({ type: 'session.ready', realtime_kind: 'conversation', input_sample_rate_hz: 24000, output_sample_rate_hz: 24000 });
		await screen.findByText(t('realtimeVoice.connectedMicrophoneOn'));
		socket.message({ type: 'error', code, message: 'Do not expose raw provider text' });
		await screen.findByText(t(message));
		expect(track.stop).not.toHaveBeenCalled();
		expect(socket.closed).toBe(false);
		expect(socket.sent).toEqual([]);
		socket.message({ type: 'transcript.output.delta', delta: 'Response continues' });
		await screen.findByText('Response continues');
		socket.close();
		socket.onclose?.();
		await screen.findByText(t('realtimeVoice.connectionClosed'));
		expect(track.stop).toHaveBeenCalledTimes(1);
	});

	it('converts a WebP pick within both wire limits and fences encoding when permissions change', async () => {
		const webp = new File(['webp fixture'], 'reference.webp', { type: 'image/webp' });
		const close = vi.fn();
		const decode = vi.fn().mockResolvedValue({ width: 4096, height: 2048, close });
		vi.stubGlobal('createImageBitmap', decode);
		const drawImage = vi.fn();
		vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D);
		const encode = vi.spyOn(HTMLCanvasElement.prototype, 'toBlob')
			.mockImplementationOnce((respond) => respond(new Blob([new Uint8Array(1024 * 1024 + 1)], { type: 'image/png' })))
			.mockImplementationOnce((respond) => respond(new Blob([new Uint8Array(900 * 1024)], { type: 'image/png' })));
		const track = { stop: vi.fn(), enabled: true };
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
		calls.capabilities.mockResolvedValue({ ...capability(), realtime_image_input: true });
		calls.createSession.mockResolvedValue({ provider_type: 'openai', realtime_image_input: true });
		render(RealtimeVoice);
		const send = await screen.findByRole('button', { name: t('realtimeImage.send') });
		expect(send).toHaveProperty('disabled', true);
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.startSession') }));
		await waitFor(() => expect(Socket.instances).toHaveLength(1));
		const socket = Socket.instances[0];
		socket.open();
		socket.message({ type: 'session.ready', realtime_kind: 'conversation', input_sample_rate_hz: 24000, output_sample_rate_hz: 24000 });
		await screen.findByText(t('realtimeVoice.connectedMicrophoneOn'));
		const input = screen.getByLabelText(t('realtimeImage.send'));
		await fireEvent.change(input, { target: { files: [webp] } });
		await waitFor(() => expect(socket.sent).toHaveLength(1));
		const frame = JSON.parse(socket.sent[0]);
		expect(frame.type).toBe('conversation.input_image');
		expect(frame.image_url).toMatch(/^data:image\/png;base64,/);
		expect(atob(frame.image_url.split(',')[1]).length).toBe(900 * 1024);
		expect(new TextEncoder().encode(socket.sent[0]).length).toBeLessThan(2 * 1024 * 1024);
		expect(drawImage.mock.calls.map((call) => call.slice(-2))).toEqual([[2048, 1024], [1024, 512]]);
		expect(encode).toHaveBeenLastCalledWith(expect.any(Function), 'image/png', 0.86);
		expect(close).toHaveBeenCalledTimes(1);
		const pending = Promise.withResolvers<ImageBitmap>();
		decode.mockReturnValueOnce(pending.promise);
		encode.mockImplementationOnce((respond) => respond(new Blob(['png'], { type: 'image/png' })));
		await fireEvent.change(input, { target: { files: [webp] } });
		pendingLumen();
		pending.resolve({ width: 10, height: 10, close } as unknown as ImageBitmap);
		await waitFor(() => expect(close).toHaveBeenCalledTimes(2));
		expect(socket.sent).toHaveLength(1);
	});

	it('does not send images when admission omits the capability', async () => {
		const track = { stop: vi.fn(), enabled: true };
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
		calls.capabilities.mockResolvedValue({ ...capability(), realtime_image_input: true });
		render(RealtimeVoice);
		await screen.findByText(t('realtimeVoice.ready'));
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.startSession') }));
		await waitFor(() => expect(Socket.instances).toHaveLength(1));
		const socket = Socket.instances[0];
		socket.open();
		socket.message({ type: 'session.ready', realtime_kind: 'conversation', input_sample_rate_hz: 24000, output_sample_rate_hz: 24000 });
		await screen.findByText(t('realtimeVoice.connectedMicrophoneOn'));
		expect(screen.getByRole('button', { name: t('realtimeImage.send') })).toHaveProperty('disabled', true);
		expect(socket.sent).toHaveLength(0);
	});
	it.each(['translation', 'live'] as const)('admits and drains %s without conversation-only commands', async (kind) => {
		const track = { stop: vi.fn(), enabled: true };
		const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [track] });
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia } });
		calls.capabilities.mockResolvedValue({
			...capability(), realtime_kind: kind,
			...(kind === 'translation' ? { available_voices: [], default_voice: null, realtime_session_fields: ['output_language'] } :
				{ available_voices: ['marin'], default_voice: 'marin', realtime_session_fields: ['voice', 'instructions'] })
		});
		render(RealtimeVoice);
		await screen.findByText(`${t('realtimeTranscription.mode')}: ${t(kind === 'translation' ? 'realtimeModes.translation' : 'realtimeModes.live')}`);
		const start = screen.getByRole('button', { name: t('realtimeVoice.startSession') });
		if (kind === 'translation') {
			await fireEvent.click(start);
			expect(getUserMedia).not.toHaveBeenCalled();
			expect(screen.queryByLabelText(t('realtimeVoice.voice'))).toBeNull();
			await fireEvent.input(screen.getByLabelText(t('realtimeModes.outputLanguage')), { target: { value: 'es' } });
		} else {
			await fireEvent.input(screen.getByLabelText(t('realtimeModes.instructions')), { target: { value: 'Speak slowly' } });
		}
		await fireEvent.click(start);
		await waitFor(() => expect(Socket.instances).toHaveLength(1));
		const call = calls.createSession.mock.calls[0];
		expect([call[1], call[5], call[6]]).toEqual(kind === 'translation'
			? [null, kind, { output_language: 'es', max_duration_seconds: 300 }]
			: ['marin', kind, { instructions: 'Speak slowly', max_duration_seconds: 300 }]);
		const socket = Socket.instances[0];
		socket.open();
		socket.message({ type: 'session.ready', realtime_kind: kind, input_sample_rate_hz: 24000, output_sample_rate_hz: 24000 });
		await screen.findByText(t('realtimeVoice.connectedMicrophoneOn'));
		expect(screen.queryByRole('button', { name: t('realtimeVoice.interrupt') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('realtimeTranscription.commit') })).toBeNull();
		Capture.current?.port.onmessage?.({ data: new Int16Array([1, 2]).buffer } as MessageEvent<ArrayBuffer>);
		if (kind === 'live') {
			await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.microphoneOff') }));
			await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.microphoneOn') }));
		}
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.endSession') }));
		await waitFor(() => expect(socket.sent.map((value) => JSON.parse(value).type)).toEqual([
			'audio.input.append', ...(kind === 'live' ? ['audio.input.mute', 'audio.input.unmute'] : []), 'session.close'
		]));
		expect(track.stop).toHaveBeenCalled();
		expect(socket.closed).toBe(false);
		socket.message({ type: 'transcript.output.delta', delta: 'Final words' });
		socket.message({ type: 'session.closed' });
		expect(await screen.findByText('Final words')).toBeTruthy();
		expect(socket.closed).toBe(true);
	});
	it.each(['translation', 'live'] as const)('clears %s drafts on a project switch', async (kind) => {
		calls.capabilities.mockResolvedValue({
			...capability(), realtime_kind: kind,
			...(kind === 'translation' ? { available_voices: [], default_voice: null, realtime_session_fields: ['output_language'] } :
				{ available_voices: ['marin'], default_voice: 'marin', realtime_session_fields: ['voice', 'instructions'] })
		});
		const label = t(kind === 'translation' ? 'realtimeModes.outputLanguage' : 'realtimeModes.instructions');
		render(RealtimeVoice);
		const input = await screen.findByRole('textbox', { name: label }) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: kind === 'translation' ? 'es' : 'private session draft' } });
		const response = Promise.withResolvers<unknown>();
		calls.capabilities.mockReturnValueOnce(response.promise);
		setVerifiedLumenActor(user('project-2'));
		await waitFor(() => expect(screen.queryByRole('textbox', { name: label })).toBeNull());
		response.resolve({ ...capability(), realtime_kind: kind, realtime_session_fields: ['output_language', 'instructions'] });
		expect((await screen.findByRole('textbox', { name: label }) as HTMLInputElement).value).toBe('');
	});

	it('shows only advertised conversation reasoning and forwards the chosen effort', async () => {
		const track = { stop: vi.fn(), enabled: true };
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
		calls.capabilities.mockResolvedValue({
			...capability(), realtime_kind: 'conversation', realtime_session_fields: ['voice', 'reasoning_effort'],
			available_reasoning_efforts: ['low', 'xhigh', 'none'], default_reasoning_effort: 'low'
		});
		render(RealtimeVoice);
		const effort = await screen.findByLabelText(chatT('input.reasoningEffort'));
		expect(Array.from((effort as HTMLSelectElement).options, (option) => option.value)).toEqual(['', 'low', 'xhigh']);
		await fireEvent.change(effort, { target: { value: 'xhigh' } });
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.startSession') }));
		await waitFor(() => expect(calls.createSession.mock.calls[0]?.[6]).toEqual({ reasoning_effort: 'xhigh', max_duration_seconds: 300 }));
	});

	it('reports unconfirmed Live usage if the connection closes without a terminal frame', async () => {
		const track = { stop: vi.fn(), enabled: true };
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
		calls.capabilities.mockResolvedValue({ ...capability(), realtime_kind: 'live' });
		render(RealtimeVoice);
		await screen.findByText(t('realtimeVoice.ready'));
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.startSession') }));
		await waitFor(() => expect(Socket.instances).toHaveLength(1));
		const socket = Socket.instances[0];
		socket.open();
		socket.message({ type: 'session.ready', realtime_kind: 'live', input_sample_rate_hz: 24000, output_sample_rate_hz: 24000 });
		await screen.findByText(t('realtimeVoice.connectedMicrophoneOn'));
		socket.close();
		socket.onclose?.();
		expect(await screen.findByText(t('realtimeModes.usageUnconfirmed'))).toBeTruthy();
		expect(screen.queryByText(t('realtimeTranscription.ended'))).toBeNull();
		expect(track.stop).toHaveBeenCalled();
	});
	it('does not acquire a microphone or create a session with chat-only authority', async () => {
		grantLumen('lumen-chat_user');
		const microphone = vi.fn();
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: microphone } });
		render(RealtimeVoice);
		await fireEvent.click(screen.getByRole('button', { name: '음성 세션 시작' }));
		expect(microphone).not.toHaveBeenCalled();
		expect(calls.createSession).not.toHaveBeenCalled();
	});
	it.each(['', 'permission lookup failed'])('keeps an active session but pauses input and masks transcripts through refresh (%s)', async (permissionError) => {
		const track = { stop: vi.fn(), enabled: true };
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
		render(RealtimeVoice);
		await screen.findByText(t('realtimeVoice.ready'));
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.startSession') }));
		await waitFor(() => expect(Socket.instances).toHaveLength(1));
		const socket = Socket.instances[0];
		socket.open();
		socket.message({ type: 'session.ready', input_sample_rate_hz: 24000, output_sample_rate_hz: 24000 });
		await screen.findByText(t('realtimeVoice.connectedMicrophoneOn'));
		socket.message({ type: 'transcript.input.delta', delta: 'preserved input' });
		socket.message({ type: 'transcript.output.delta', delta: 'preserved output' });
		await screen.findByText('preserved output');
		const context = Context.current;
		const capture = Capture.current;
		pendingLumen(permissionError);
		refreshLumenAuth('refreshed-token');
		await waitFor(() => expect(track.enabled).toBe(false));
		expect(track.stop).not.toHaveBeenCalled();
		expect(context?.close).not.toHaveBeenCalled();
		expect(socket.closed).toBe(false);
		expect(screen.queryByText('preserved input')).toBeNull();
		expect(screen.queryByText('preserved output')).toBeNull();
		expect(screen.getByRole('button', { name: t('realtimeVoice.endSession') }).hasAttribute('disabled')).toBe(false);
		expect(screen.getByRole('combobox', { name: t('realtimeVoice.model') }).hasAttribute('disabled')).toBe(true);
		const pcm = new Int16Array([-32768, 32767]);
		capture?.port.onmessage?.({ data: pcm.buffer } as MessageEvent<ArrayBuffer>);
		socket.message({ type: 'transcript.output.delta', delta: ' forbidden new output' });
		socket.message({ type: 'audio.output.delta', delta: 'AID/fw==', sample_rate_hz: 24000 });
		expect(socket.sent).toHaveLength(0);
		expect(context?.source.start).not.toHaveBeenCalled();
		grantLumen('lumen-audio_user');
		await waitFor(() => expect(track.enabled).toBe(true));
		expect(screen.getByText('preserved input')).toBeTruthy();
		expect(screen.getByText('preserved output')).toBeTruthy();
		expect(Context.current).toBe(context);
		expect(Capture.current).toBe(capture);
		capture?.port.onmessage?.({ data: pcm.buffer } as MessageEvent<ArrayBuffer>);
		expect(JSON.parse(socket.sent[0]).type).toBe('audio.input.append');
		expect(calls.createSession).toHaveBeenCalledTimes(1);
		expect(calls.models).toHaveBeenCalledTimes(1);
		expect(calls.capabilities).toHaveBeenCalledTimes(1);
		// Explicit local mute must survive the next grant reload too.
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.microphoneOff') }));
		expect(track.enabled).toBe(false);
		pendingLumen();
		await screen.findByText(t('realtimeVoice.connectedMuted'));
		expect(screen.getByRole('button', { name: t('realtimeVoice.microphoneOn') }).hasAttribute('disabled')).toBe(true);
		grantLumen('lumen-audio_user');
		await waitFor(() => expect(screen.getByRole('button', { name: t('realtimeVoice.microphoneOn') }).hasAttribute('disabled')).toBe(false));
		expect(track.enabled).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.endSession') }));
		expect(track.stop).toHaveBeenCalled();
		expect(socket.closed).toBe(true);
	});

	it.each(['revocation', 'project', 'user', 'logout', 'switching'] as const)('tears down an active session immediately on definitive %s', async (transition) => {
		const track = { stop: vi.fn(), enabled: true };
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
		render(RealtimeVoice);
		await screen.findByText(t('realtimeVoice.ready'));
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.startSession') }));
		await waitFor(() => expect(Socket.instances).toHaveLength(1));
		const socket = Socket.instances[0];
		socket.open();
		socket.message({ type: 'session.ready', input_sample_rate_hz: 24000, output_sample_rate_hz: 24000 });
		await screen.findByText(t('realtimeVoice.connectedMicrophoneOn'));
		socket.message({ type: 'transcript.output.delta', delta: 'private transcript' });
		await screen.findByText('private transcript');
		const context = Context.current;
		pendingLumen();
		await waitFor(() => expect(track.enabled).toBe(false));
		if (transition === 'revocation') grantLumen('lumen-chat_user');
		else if (transition === 'project') setVerifiedLumenActor(user('project-2'));
		else if (transition === 'user') setVerifiedLumenActor({ ...user('project-1'), userId: 'another-user' });
		else if (transition === 'logout') authReady.set(false);
		else projectSwitching.set(true);
		await waitFor(() => expect(track.stop).toHaveBeenCalled());
		expect(context?.close).toHaveBeenCalled();
		expect(socket.closed).toBe(true);
		expect(screen.queryByText('private transcript')).toBeNull();
		grantLumen('lumen-audio_user');
		await waitFor(() => expect(screen.getByRole('button', { name: t('realtimeVoice.endSession') }).hasAttribute('disabled')).toBe(true));
		expect(screen.queryByText('private transcript')).toBeNull();
		expect(calls.createSession).toHaveBeenCalledTimes(1);
	});

	it('rechecks the current grant after microphone acquisition before paid session admission', async () => {
		const microphone = Promise.withResolvers<MediaStream>();
		const track = { stop: vi.fn(), enabled: true };
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockReturnValue(microphone.promise) } });
		render(RealtimeVoice);
		await screen.findByText(t('realtimeVoice.ready'));
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.startSession') }));
		pendingLumen();
		microphone.resolve({ getTracks: () => [track] } as unknown as MediaStream);
		await waitFor(() => expect(track.stop).toHaveBeenCalled());
		expect(calls.createSession).not.toHaveBeenCalled();
		expect(calls.connect).not.toHaveBeenCalled();
	});

	it('does not connect a newly admitted session whose response arrives while pending', async () => {
		const admission = Promise.withResolvers<{ session_id: string; status: string; provider_type: string; ticket: string; websocket_path: string }>();
		calls.createSession.mockReturnValueOnce(admission.promise);
		const track = { stop: vi.fn(), enabled: true };
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
		render(RealtimeVoice);
		await screen.findByText(t('realtimeVoice.ready'));
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.startSession') }));
		await waitFor(() => expect(calls.createSession).toHaveBeenCalledTimes(1));
		pendingLumen();
		admission.resolve({ session_id: 'unpublished', status: 'ready', provider_type: 'openai', ticket: 'opaque', websocket_path: '/api/v1/chat/realtime/ws' });
		await waitFor(() => expect(track.stop).toHaveBeenCalled());
		expect(calls.connect).not.toHaveBeenCalled();
		grantLumen('lumen-audio_user');
		await waitFor(() => expect(screen.getByRole('button', { name: t('realtimeVoice.startSession') }).hasAttribute('disabled')).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.startSession') }));
		await waitFor(() => expect(calls.createSession).toHaveBeenCalledTimes(2));
		expect(calls.createSession.mock.calls[1][3]).toBe(calls.createSession.mock.calls[0][3]);
	});
	it('allows local session termination while permissions remain pending', async () => {
		const track = { stop: vi.fn(), enabled: true };
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
		render(RealtimeVoice);
		await screen.findByText(t('realtimeVoice.ready'));
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.startSession') }));
		await waitFor(() => expect(Socket.instances).toHaveLength(1));
		const socket = Socket.instances[0];
		socket.open();
		socket.message({ type: 'session.ready', input_sample_rate_hz: 24000, output_sample_rate_hz: 24000 });
		await screen.findByText(t('realtimeVoice.connectedMicrophoneOn'));
		const context = Context.current;
		pendingLumen();
		await waitFor(() => expect(track.enabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.endSession') }));
		expect(socket.closed).toBe(true);
		expect(track.stop).toHaveBeenCalled();
		expect(context?.close).toHaveBeenCalled();
		expect(screen.getByRole('button', { name: t('realtimeVoice.endSession') }).hasAttribute('disabled')).toBe(true);
	});
	it('does not admit a session after local cancellation and stops a late microphone stream', async () => {
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
			{ token: 'token', projectId: 'project-1' }, expect.any(String), expect.any(AbortSignal), 'conversation', { max_duration_seconds: 300 }));
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
		setVerifiedLumenActor(user('project-2'));
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

	it('reports denied microphone access without inventing an applied connection or unknown provider outcome', async () => {
		const getUserMedia = vi.fn().mockRejectedValue(new DOMException('denied', 'NotAllowedError'));
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia } });
		const state = vi.spyOn(experience, 'experienceState');
		const discarded = vi.spyOn(experience, 'experienceDiscarded');
		const applied = vi.spyOn(experience, 'experienceApplied');
		try {
			render(RealtimeVoice);
			await screen.findByText('음성 입력·출력 경로와 가격이 준비되었습니다.');
			applied.mockClear();
			await fireEvent.click(screen.getByRole('button', { name: '음성 세션 시작' }));
			await screen.findByText('마이크 권한이 거부되었습니다.');
			expect(calls.createSession).not.toHaveBeenCalled();
			expect(screen.getByRole('button', { name: '음성 세션 시작' }).hasAttribute('disabled')).toBe(false);
			expect(state.mock.calls.filter(([, , step]) => step !== undefined && step >= 2).map(([, value, step]) => [value, step])).toEqual([['loading', 2], ['error', 5]]);
			expect(discarded).not.toHaveBeenCalled();
			expect(applied).not.toHaveBeenCalled();
		} finally { state.mockRestore(); discarded.mockRestore(); applied.mockRestore(); }
	});

	it.each(['gpt-realtime-whisper', 'gpt-transcribe'])('commits PCM and retains terminal transcription for %s', async (modelName) => {
		calls.models.mockResolvedValue([{ ...model(), model_name: modelName, display_name: modelName }]);
		calls.capabilities.mockResolvedValue({ ...capability(), realtime_kind: 'transcription', available_voices: [], default_voice: null, output_sample_rate_hz: 0 });
		const track = { stop: vi.fn(), enabled: true };
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
		render(RealtimeVoice);
		await screen.findByText(t('realtimeTranscription.ready'));
		expect(screen.getByRole('option', { name: modelName })).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('realtimeImage.send') })).toBeNull();
		expect(screen.queryByRole('combobox', { name: t('realtimeVoice.voice') })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeTranscription.start') }));
		await waitFor(() => expect(Socket.instances).toHaveLength(1));
		expect(calls.createSession).toHaveBeenCalledWith(17, null, expect.anything(), expect.any(String), expect.any(AbortSignal), 'transcription', { max_duration_seconds: 300 });
		const socket = Socket.instances[0];
		socket.open();
		socket.message({ type: 'session.ready', realtime_kind: 'transcription', input_sample_rate_hz: 24000, output_sample_rate_hz: 0 });
		await screen.findByText(t('realtimeVoice.connectedMicrophoneOn'));
		Capture.current?.port.onmessage?.({ data: new Int16Array([10, -10]).buffer } as MessageEvent<ArrayBuffer>);
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeTranscription.commit') }));
		await waitFor(() => expect(socket.sent.map((frame) => JSON.parse(frame).type)).toContain('audio.input.commit'));
		socket.message({ type: 'transcript.input.delta', item_id: 'turn-1', delta: '미확정' });
		await screen.findByText(t('realtimeTranscription.partial'));
		expect(screen.queryByText(t('realtimeTranscription.final'))).toBeNull();
		socket.message({ type: 'transcript.input.completed', item_id: 'turn-1', text: '확정 문장' });
		await screen.findByText('확정 문장');
		expect(screen.queryByText('미확정')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeVoice.endSession') }));
		await screen.findByText(t('realtimeTranscription.ending'));
		expect(track.stop).toHaveBeenCalled();
		expect(socket.closed).toBe(false);
		socket.message({ type: 'session.closed' });
		await screen.findByText(t('realtimeTranscription.ended'));
		expect(screen.getByText('확정 문장')).toBeTruthy();
		expect(socket.closed).toBe(true);
		expect(Context.current?.source.start).not.toHaveBeenCalled();
		setVerifiedLumenActor(user('project-2'));
		await waitFor(() => expect(screen.queryByText('확정 문장')).toBeNull());
	});

	it('never promotes a partial or failed transcription to final when its socket closes unexpectedly', async () => {
		calls.capabilities.mockResolvedValue({ ...capability(), realtime_kind: 'transcription', available_voices: [], default_voice: null, output_sample_rate_hz: 0 });
		const stopTrack = vi.fn();
		vi.stubGlobal('navigator', { userAgent: navigator.userAgent, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] }) } });
		render(RealtimeVoice);
		await screen.findByText(t('realtimeTranscription.ready'));
		await fireEvent.click(screen.getByRole('button', { name: t('realtimeTranscription.start') }));
		await waitFor(() => expect(Socket.instances).toHaveLength(1));
		const socket = Socket.instances[0]; socket.open();
		socket.message({ type: 'session.ready', realtime_kind: 'transcription', input_sample_rate_hz: 24000, output_sample_rate_hz: 0 });
		await screen.findByText(t('realtimeVoice.connectedMicrophoneOn'));
		socket.message({ type: 'transcript.input.delta', item_id: 'turn-1', delta: 'partial text' });
		socket.message({ type: 'transcript.input.failed', item_id: 'turn-1' });
		await screen.findByText(t('realtimeTranscription.failed'));
		socket.onclose?.();
		await screen.findByText(t('realtimeVoice.connectionClosed'));
		expect(screen.getByText('partial text')).toBeTruthy();
		expect(screen.queryByText(t('realtimeTranscription.final'))).toBeNull();
		expect(screen.getByText(t('realtimeTranscription.unfinished'))).toBeTruthy();
		expect(stopTrack).toHaveBeenCalled();
	});
});
