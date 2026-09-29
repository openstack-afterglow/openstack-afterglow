import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import type * as AudioModule from '$lib/api/audioStudio';
import AudioStudio from '../AudioStudio.svelte';

const calls = vi.hoisted(() => ({ models: vi.fn(), capabilities: vi.fn(), speech: vi.fn(), upload: vi.fn(), transcribe: vi.fn(), goto: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: calls.goto }));
vi.mock('$lib/api/audioStudio', async (original) => ({ ...await original<typeof AudioModule>(), audioStudioApi: calls }));
const gate = (feature: 'audio_output' | 'audio_input', pricing_available = true) => ({ feature_gates: { [feature]: { available: true, mode: 'native', pricing_available, reason_code: null } } });
const model = (kind: 'tts' | 'stt', pricing = true) => ({ id: kind === 'tts' ? 17 : 19, model_kind: kind, model_name: kind, display_name: kind === 'tts' ? 'Speech model' : 'Transcription model', provider_api_key_configured: true, capabilities: gate(kind === 'tts' ? 'audio_output' : 'audio_input', pricing) });
const user = (projectId: string) => ({ token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'owner', username: 'tester', projectId, projectName: projectId, availableProjects: [], roles: [], isSystemAdmin: false, federated: false });

beforeEach(() => {
	vi.clearAllMocks();
	auth.set(user('project-1'));
	calls.models.mockImplementation(async (kind: 'tts' | 'stt') => [model(kind)]);
	calls.capabilities.mockImplementation(async (kind: 'tts' | 'stt', id: number) => ({ model_id: id, model_kind: kind, model_capabilities: gate(kind === 'tts' ? 'audio_output' : 'audio_input'), ...(kind === 'tts' ? { available_voices: ['alloy', 'nova'], available_formats: ['mp3', 'wav'] } : {}) }));
	calls.speech.mockResolvedValue(new Blob(['FAKE-AUDIO-BYTES'], { type: 'audio/mpeg' }));
	calls.upload.mockResolvedValue({ id: 'scanned-asset', name: 'voice.wav', mime_type: 'audio/wav' });
	calls.transcribe.mockResolvedValue('인식된 문장');
	vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: vi.fn(() => 'blob:audio-test'), revokeObjectURL: vi.fn() }));
	vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('Audio Studio', () => {
	it('plays real Blob bytes, downloads them, reuses an ambiguous speech intent and revokes playback on owner switch', async () => {
		calls.speech.mockRejectedValueOnce(new Error('lost response'));
		const view = render(AudioStudio);
		await screen.findByText('음성 생성 경로와 가격이 준비되었습니다.');
		await fireEvent.input(screen.getByRole('textbox', { name: /읽을 텍스트/ }), { target: { value: 'Hello world' } });
		await fireEvent.change(screen.getByLabelText('목소리'), { target: { value: 'nova' } });
		await fireEvent.change(screen.getByLabelText('형식'), { target: { value: 'wav' } });
		await fireEvent.click(screen.getByRole('button', { name: '음성 생성' }));
		await screen.findByText('lost response');
		await fireEvent.click(screen.getByRole('button', { name: '음성 생성' }));
		const link = await screen.findByRole('link', { name: '음성 다운로드' });
		expect(link.getAttribute('href')).toBe('blob:audio-test');
		expect(link.getAttribute('download')).toBe('speech.wav');
		expect(calls.speech.mock.calls[0][0]).toMatchObject({ model_id: '17', input: 'Hello world', voice: 'nova', response_format: 'wav' });
		expect(calls.speech.mock.calls[1][2]).toBe(calls.speech.mock.calls[0][2]);
		expect(calls.speech.mock.calls[1][2]).toMatch(/^[0-9a-f-]{36}$/);
		expect(URL.createObjectURL).toHaveBeenCalledWith(expect.objectContaining({ size: 16 }));
		auth.set(user('project-2'));
		await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:audio-test'));
		expect(screen.queryByRole('link', { name: '음성 다운로드' })).toBeNull();
		view.unmount();
	});

	it('uses the selected Gemini model voice and WAV-only format from capabilities', async () => {
		calls.models.mockImplementation(async (kind: 'tts' | 'stt') => kind === 'tts' ? [model('tts'), { ...model('tts'), id: 18, model_name: 'gemini-speech', display_name: 'Gemini speech' }] : [model('stt')]);
		calls.capabilities.mockImplementation(async (kind: 'tts' | 'stt', id: number) => ({ model_id: id, model_kind: kind, model_capabilities: gate(kind === 'tts' ? 'audio_output' : 'audio_input'), ...(kind === 'tts' ? { available_voices: id === 18 ? ['Puck', 'Zephyr'] : ['alloy', 'nova'], available_formats: id === 18 ? ['wav'] : ['mp3', 'wav'] } : {}) }));
		render(AudioStudio);
		await screen.findByText('음성 생성 경로와 가격이 준비되었습니다.');
		await fireEvent.change(screen.getByLabelText('음성 모델'), { target: { value: '18' } });
		await waitFor(() => expect((screen.getByLabelText('목소리') as HTMLSelectElement).value).toBe('Puck'));
		expect((screen.getByLabelText('형식') as HTMLSelectElement).value).toBe('wav');
		expect(screen.getByRole('option', { name: 'Zephyr' })).toBeTruthy();
		expect(screen.queryByRole('option', { name: 'MP3' })).toBeNull();
		await fireEvent.input(screen.getByRole('textbox', { name: /읽을 텍스트/ }), { target: { value: 'Hello Gemini' } });
		await fireEvent.click(screen.getByRole('button', { name: '음성 생성' }));
		await waitFor(() => expect(calls.speech).toHaveBeenCalledWith({ model_id: '18', input: 'Hello Gemini', voice: 'Puck', response_format: 'wav' }, { token: 'token', projectId: 'project-1' }, expect.any(String), expect.any(AbortSignal)));
	});

	it('uploads scanned audio then transcribes with the selected model and exposes copy/chat handoff', async () => {
		render(AudioStudio);
		await screen.findByText('음성 인식 경로와 가격이 준비되었습니다.');
		const file = new File(['FAKE-WAV'], 'voice.wav', { type: 'audio/wav' });
		await fireEvent.change(screen.getByLabelText('음성 파일'), { target: { files: [file] } });
		await screen.findByText('검사된 입력: voice.wav');
		expect(calls.upload).toHaveBeenCalledWith(file, { token: 'token', projectId: 'project-1' }, expect.any(AbortSignal));
		await fireEvent.input(screen.getByLabelText('언어 코드 (선택)'), { target: { value: 'ko' } });
		calls.transcribe.mockRejectedValueOnce(new Error('lost transcription'));
		await fireEvent.click(screen.getByRole('button', { name: '텍스트로 변환' }));
		await screen.findByText('lost transcription');
		await fireEvent.click(screen.getByRole('button', { name: '텍스트로 변환' }));
		await screen.findByText('인식된 문장');
		expect(calls.transcribe.mock.calls[0][0]).toMatchObject({ model_id: '19', input_asset_id: 'scanned-asset', language: 'ko' });
		expect(calls.transcribe.mock.calls[1][2]).toBe(calls.transcribe.mock.calls[0][2]);
		expect(calls.transcribe.mock.calls[1][2]).toMatch(/^[0-9a-f-]{36}$/);
		await fireEvent.click(screen.getByRole('button', { name: '채팅 입력에 넣기' }));
		expect(calls.goto).toHaveBeenCalledWith('/dashboard/chat');
	});

	it('reports microphone denial without uploading or recording automatically', async () => {
		const getUserMedia = vi.fn().mockRejectedValue(new DOMException('denied', 'NotAllowedError'));
		vi.stubGlobal('navigator', Object.assign(Object.create(navigator), { mediaDevices: { getUserMedia } }));
		vi.stubGlobal('MediaRecorder', class {});
		render(AudioStudio);
		await screen.findByText('음성 인식 경로와 가격이 준비되었습니다.');
		expect(getUserMedia).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '마이크 녹음' }));
		await screen.findByText('마이크 권한이 거부되었습니다. 브라우저 권한을 확인하거나 파일을 선택하세요.');
		expect(calls.upload).not.toHaveBeenCalled();
	});

	it('records only after permission, stops tracks and uploads recorded bytes as a scanned asset', async () => {
		const stop = vi.fn();
		const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] });
		vi.stubGlobal('navigator', Object.assign(Object.create(navigator), { mediaDevices: { getUserMedia } }));
		class Recorder {
			static isTypeSupported = (mime: string) => mime === 'audio/webm';
			mimeType = 'audio/webm;codecs=opus';
			state = 'inactive';
			ondataavailable: ((event: { data: Blob }) => void) | null = null;
			onstop: (() => void) | null = null;
			onerror: (() => void) | null = null;
			start() { this.state = 'recording'; }
			stop() { this.ondataavailable?.({ data: new Blob(['recorded bytes']) }); this.state = 'inactive'; this.onstop?.(); }
		}
		vi.stubGlobal('MediaRecorder', Recorder);
		render(AudioStudio);
		await screen.findByText('음성 인식 경로와 가격이 준비되었습니다.');
		await fireEvent.click(screen.getByRole('button', { name: '마이크 녹음' }));
		await screen.findByText('녹음 중 · 종료하면 업로드합니다.');
		await fireEvent.click(screen.getByRole('button', { name: '녹음 종료' }));
		await waitFor(() => expect(calls.upload).toHaveBeenCalled());
		const file: File = calls.upload.mock.calls[0][0];
		expect(file.type).toBe('audio/webm');
		expect(file.size).toBe(14);
		expect(file.name).toBe('recording.webm');
		expect(stop).toHaveBeenCalled();
	});

	it('refuses unpriced and unsupported routes, and drops stale asset responses on project change', async () => {
		calls.models.mockImplementation(async (kind: 'tts' | 'stt') => [model(kind, false)]);
		render(AudioStudio);
		await screen.findAllByText('오디오 가격이 설정되지 않았습니다.');
		await fireEvent.input(screen.getByRole('textbox', { name: /읽을 텍스트/ }), { target: { value: 'not charged' } });
		expect(screen.getByRole('button', { name: '음성 생성' }).hasAttribute('disabled')).toBe(true);
		expect(calls.speech).not.toHaveBeenCalled();
		const { promise, resolve } = Promise.withResolvers<{ id: string; name: string }>();
		calls.upload.mockImplementationOnce(() => promise);
		await fireEvent.change(screen.getByLabelText('음성 파일'), { target: { files: [new File(['abc'], 'first.wav', { type: 'audio/wav' })] } });
		auth.set(user('project-2'));
		resolve({ id: 'old-asset', name: 'first.wav' });
		await waitFor(() => expect(calls.models).toHaveBeenCalledWith('stt', { token: 'token', projectId: 'project-2' }));
		expect(screen.queryByText('검사된 입력: first.wav')).toBeNull();
	});
});
