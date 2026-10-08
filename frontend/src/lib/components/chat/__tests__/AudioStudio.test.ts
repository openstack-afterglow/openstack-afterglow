import { grantLumen, pendingLumen } from './lumenPermissionFixture';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { takeAudioTranscript } from '$lib/api/audioChatHandoff';
import type * as AudioModule from '$lib/api/audioStudio';
import AudioStudio from '../AudioStudio.svelte';
import { t } from '$lib/i18n/ns/chat-studio';
import { initLocale } from '$lib/i18n/runtime.svelte';

const calls = vi.hoisted(() => ({ models: vi.fn(), capabilities: vi.fn(), speech: vi.fn(), upload: vi.fn(), transcribe: vi.fn(), goto: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: calls.goto }));
vi.mock('$lib/api/audioStudio', async (original) => ({ ...await original<typeof AudioModule>(), audioStudioApi: calls }));
const gate = (feature: 'audio_output' | 'audio_input', pricing_available = true) => ({ feature_gates: { [feature]: { available: true, mode: 'native', pricing_available, reason_code: null } } });
const model = (kind: 'tts' | 'stt', pricing = true) => ({ id: kind === 'tts' ? 17 : 19, model_kind: kind, model_name: kind, display_name: kind === 'tts' ? 'Speech model' : 'Transcription model', provider_api_key_configured: true, capabilities: gate(kind === 'tts' ? 'audio_output' : 'audio_input', pricing) });
const user = (projectId: string) => ({ token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'owner', username: 'tester', projectId, projectName: projectId, availableProjects: [], roles: [], isSystemAdmin: false, federated: false });
const capability = (kind: 'tts' | 'stt', id: number, timestamps = true) => ({
	model_id: id,
	model_kind: kind,
	model_capabilities: gate(kind === 'tts' ? 'audio_output' : 'audio_input'),
	...(kind === 'tts' ? { available_voices: ['alloy', 'nova'], available_formats: ['mp3', 'wav'] } : { available_timestamp_granularities: timestamps ? ['segment'] : [] })
});
const timed = { text: '인식된 문장 둘째 문장', segments: [{ start: 1.2, end: 3.8, text: '인식된 문장' }, { start: 4.1, end: 6.5, text: '둘째 문장' }] };
let created: Array<{ url: string; blob: Blob }> = [];
const blobAt = (url: string | null) => created.find((item) => item.url === url)?.blob as Blob;
const readBlob = (blob: Blob) => new Promise<string>((resolve, reject) => {
	const reader = new FileReader();
	reader.onload = () => resolve(String(reader.result));
	reader.onerror = () => reject(reader.error);
	reader.readAsText(blob);
});
async function openStt() {
	await fireEvent.click(screen.getByRole('tab', { name: '음성 → 텍스트' }));
	await screen.findByText('음성 인식 경로와 가격이 준비되었습니다.');
}
async function chooseAudio(file: File) {
	await fireEvent.change(screen.getByLabelText('음성 파일 선택'), { target: { files: [file] } });
	await screen.findByText('검사된 입력: voice.wav');
}

beforeEach(() => {
	vi.clearAllMocks();
	created = [];
	auth.set(user('project-1'));
	calls.models.mockImplementation(async (kind: 'tts' | 'stt') => [model(kind)]);
	calls.capabilities.mockImplementation(async (kind: 'tts' | 'stt', id: number) => capability(kind, id));
	calls.speech.mockResolvedValue(new Blob(['FAKE-AUDIO-BYTES'], { type: 'audio/mpeg' }));
	calls.upload.mockResolvedValue({ id: 'scanned-asset', name: 'voice.wav', mime_type: 'audio/wav' });
	calls.transcribe.mockResolvedValue(timed);
	vi.stubGlobal('URL', Object.assign(class extends URL {}, {
		createObjectURL: vi.fn((blob: Blob) => { const url = `blob:audio-${created.length + 1}`; created.push({ url, blob }); return url; }),
		revokeObjectURL: vi.fn()
	}));
	vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
});
// Unmount while media/URL stubs are active: teardown pauses players and revokes object URLs.
afterEach(() => { cleanup(); initLocale('ko'); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('Audio Studio', () => {
	it('denies speech generation without the independent audio leaf', async () => {
		grantLumen('lumen-chat_user', 'lumen-images_user');
		render(AudioStudio);
		await fireEvent.click(screen.getByRole('button', { name: '음성 생성' }));
		expect(calls.speech).not.toHaveBeenCalled();
		expect(calls.models).not.toHaveBeenCalled();
	});
	it.each(['', 'permission lookup failed'])('preserves speech, scanned input and transcript across same-actor refresh (%s)', async (permissionError) => {
		render(AudioStudio);
		await screen.findByText(t('audioStudio.speechReady'));
		await fireEvent.input(screen.getByRole('textbox', { name: /읽을 텍스트/ }), { target: { value: 'Keep my draft' } });
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.generateSpeech') }));
		const speechUrl = (await screen.findByRole('link', { name: t('audioStudio.downloadSpeech') })).getAttribute('href');
		await openStt();
		await chooseAudio(new File(['audio'], 'voice.wav', { type: 'audio/wav' }));
		const sourceUrl = screen.getByLabelText(t('audioStudio.previewSource', { name: 'voice.wav' })).getAttribute('src');
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.convertToText') }));
		const transcriptUrl = (await screen.findByRole('link', { name: t('audioStudio.downloadText') })).getAttribute('href');
		pendingLumen(permissionError);
		auth.set({ ...user('project-1'), token: 'refreshed-token' });
		await waitFor(() => expect(screen.getByRole('button', { name: t('audioStudio.convertToText') }).hasAttribute('disabled')).toBe(true));
		expect(screen.getByLabelText(t('audioStudio.chooseFile')).hasAttribute('disabled')).toBe(true);
		expect(screen.queryByRole('link', { name: t('audioStudio.downloadText') })).toBeNull();
		expect(URL.revokeObjectURL).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.convertToText') }));
		expect(calls.transcribe).toHaveBeenCalledTimes(1);
		grantLumen('lumen-audio_user', 'lumen-assets_editor', 'lumen-chat_user');
		expect((await screen.findByRole('link', { name: t('audioStudio.downloadText') })).getAttribute('href')).toBe(transcriptUrl);
		expect(screen.getByLabelText(t('audioStudio.previewSource', { name: 'voice.wav' })).getAttribute('src')).toBe(sourceUrl);
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.convertToText') }));
		await waitFor(() => expect(calls.transcribe).toHaveBeenLastCalledWith(expect.anything(), { token: 'refreshed-token', projectId: 'project-1' }, expect.any(String), expect.any(AbortSignal)));
		await fireEvent.click(screen.getByRole('tab', { name: t('audioStudio.textToSpeech') }));
		expect(screen.getByRole('link', { name: t('audioStudio.downloadSpeech') }).getAttribute('href')).toBe(speechUrl);
		expect((screen.getByRole('textbox', { name: /읽을 텍스트/ }) as HTMLTextAreaElement).value).toBe('Keep my draft');
		expect(calls.models).toHaveBeenCalledTimes(2);
		expect(calls.capabilities).toHaveBeenCalledTimes(2);
	});

	it('preserves an in-flight upload across refresh and does not publish a new speech response while pending', async () => {
		const upload = Promise.withResolvers<{ id: string; name: string }>();
		calls.upload.mockReturnValueOnce(upload.promise);
		render(AudioStudio);
		await openStt();
		await fireEvent.change(screen.getByLabelText(t('audioStudio.chooseFile')), { target: { files: [new File(['audio'], 'voice.wav', { type: 'audio/wav' })] } });
		const signal: AbortSignal = calls.upload.mock.calls[0][2];
		pendingLumen();
		auth.set({ ...user('project-1'), token: 'refreshed-token' });
		await waitFor(() => expect(screen.getByLabelText(t('audioStudio.chooseFile')).hasAttribute('disabled')).toBe(true));
		expect(signal.aborted).toBe(false);
		expect(URL.revokeObjectURL).not.toHaveBeenCalled();
		grantLumen('lumen-audio_user', 'lumen-assets_editor');
		upload.resolve({ id: 'scanned-asset', name: 'voice.wav' });
		await screen.findByText(t('audioStudio.scannedInput', { name: 'voice.wav' }));
		await fireEvent.click(screen.getByRole('tab', { name: t('audioStudio.textToSpeech') }));
		await fireEvent.input(screen.getByRole('textbox', { name: /읽을 텍스트/ }), { target: { value: 'Hello' } });
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.generateSpeech') }));
		const original = (await screen.findByRole('link', { name: t('audioStudio.downloadSpeech') })).getAttribute('href');
		const speech = Promise.withResolvers<Blob>();
		calls.speech.mockReturnValueOnce(speech.promise);
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.generateSpeech') }));
		pendingLumen();
		speech.resolve(new Blob(['unpublished']));
		await speech.promise;
		await waitFor(() => expect(screen.queryByRole('link', { name: t('audioStudio.downloadSpeech') })).toBeNull());
		grantLumen('lumen-audio_user', 'lumen-assets_editor');
		expect((await screen.findByRole('link', { name: t('audioStudio.downloadSpeech') })).getAttribute('href')).toBe(original);
		expect(URL.revokeObjectURL).not.toHaveBeenCalledWith(original);
	});

	it.each(['revocation', 'project', 'user', 'logout', 'switching'] as const)('releases generated speech immediately on %s', async (transition) => {
		render(AudioStudio);
		await screen.findByText(t('audioStudio.speechReady'));
		await fireEvent.input(screen.getByRole('textbox', { name: /읽을 텍스트/ }), { target: { value: 'Hello' } });
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.generateSpeech') }));
		const url = (await screen.findByRole('link', { name: t('audioStudio.downloadSpeech') })).getAttribute('href');
		if (transition === 'revocation') grantLumen('lumen-assets_editor', 'lumen-chat_user');
		else if (transition === 'project') auth.set(user('project-2'));
		else if (transition === 'user') auth.set({ ...user('project-1'), userId: 'another-user' });
		else if (transition === 'logout') authReady.set(false);
		else projectSwitching.set(true);
		await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith(url));
		expect(screen.queryByRole('link', { name: t('audioStudio.downloadSpeech') })).toBeNull();
	});

	it('releases scanned input and transcript on assets revocation without discarding generated speech', async () => {
		render(AudioStudio);
		await screen.findByText(t('audioStudio.speechReady'));
		await fireEvent.input(screen.getByRole('textbox', { name: /읽을 텍스트/ }), { target: { value: 'Hello' } });
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.generateSpeech') }));
		const speech = (await screen.findByRole('link', { name: t('audioStudio.downloadSpeech') })).getAttribute('href');
		await openStt();
		await chooseAudio(new File(['audio'], 'voice.wav', { type: 'audio/wav' }));
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.convertToText') }));
		const transcript = (await screen.findByRole('link', { name: t('audioStudio.downloadText') })).getAttribute('href');
		grantLumen('lumen-audio_user', 'lumen-chat_user');
		await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith(transcript));
		expect(screen.queryByRole('link', { name: t('audioStudio.downloadText') })).toBeNull();
		await fireEvent.click(screen.getByRole('tab', { name: t('audioStudio.textToSpeech') }));
		expect(screen.getByRole('link', { name: t('audioStudio.downloadSpeech') }).getAttribute('href')).toBe(speech);
		expect(URL.revokeObjectURL).not.toHaveBeenCalledWith(speech);
	});

	it.each(['restore', 'revoke'] as const)('keeps recording and local stop reachable while pending, then %s', async (resolution) => {
		const track = { stop: vi.fn() };
		vi.stubGlobal('navigator', Object.assign(Object.create(navigator), { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } }));
		vi.stubGlobal('MediaRecorder', class {
			static isTypeSupported = () => true;
			mimeType = 'audio/webm';
			state = 'inactive';
			ondataavailable: ((event: { data: Blob }) => void) | null = null;
			onstop: (() => void) | null = null;
			start() { this.state = 'recording'; }
			stop() { this.ondataavailable?.({ data: new Blob(['recorded bytes']) }); this.state = 'inactive'; this.onstop?.(); }
		});
		render(AudioStudio);
		await openStt();
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.recordMicrophone') }));
		await screen.findByText(t('audioStudio.recordingStatus'));
		pendingLumen();
		auth.set({ ...user('project-1'), token: 'refreshed-token' });
		const stop = await screen.findByRole('button', { name: t('audioStudio.stopRecording') });
		expect(stop.hasAttribute('disabled')).toBe(false);
		expect(track.stop).not.toHaveBeenCalled();
		if (resolution === 'restore') {
			await fireEvent.click(stop);
			expect(track.stop).toHaveBeenCalled();
			expect(calls.upload).not.toHaveBeenCalled();
			grantLumen('lumen-audio_user', 'lumen-assets_editor');
			await waitFor(() => expect(calls.upload).toHaveBeenCalledWith(expect.any(File), { token: 'refreshed-token', projectId: 'project-1' }, expect.any(AbortSignal)));
			expect((calls.upload.mock.calls[0][0] as File).size).toBe(14);
		} else {
			grantLumen('lumen-audio_user');
			await waitFor(() => expect(track.stop).toHaveBeenCalled());
			expect(calls.upload).not.toHaveBeenCalled();
			expect(screen.queryByRole('button', { name: t('audioStudio.stopRecording') })).toBeNull();
		}
	});
	it('retains the existing transcript but refuses a response settled during pending permissions, then clears source results on project change', async () => {
		render(AudioStudio);
		await openStt();
		await chooseAudio(new File(['audio'], 'voice.wav', { type: 'audio/wav' }));
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.convertToText') }));
		const url = (await screen.findByRole('link', { name: t('audioStudio.downloadText') })).getAttribute('href');
		const pending = Promise.withResolvers<typeof timed>();
		calls.transcribe.mockReturnValueOnce(pending.promise);
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.convertToText') }));
		pendingLumen();
		pending.resolve({ text: 'unpublished transcript', segments: [] });
		await pending.promise;
		await screen.findByRole('button', { name: t('audioStudio.convertToText') });
		await waitFor(() => expect(screen.queryByRole('link', { name: t('audioStudio.downloadText') })).toBeNull());
		expect(screen.queryByText('unpublished transcript')).toBeNull();
		expect(URL.revokeObjectURL).not.toHaveBeenCalledWith(url);
		grantLumen('lumen-audio_user', 'lumen-assets_editor');
		expect((await screen.findByRole('link', { name: t('audioStudio.downloadText') })).getAttribute('href')).toBe(url);
		expect(screen.queryByText('unpublished transcript')).toBeNull();
		expect(await readBlob(blobAt(url))).toContain('둘째 문장');
		expect(URL.revokeObjectURL).not.toHaveBeenCalledWith(url);
		auth.set(user('project-2'));
		await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith(url));
		expect(screen.queryByText('둘째 문장')).toBeNull();
		expect(screen.queryByLabelText(t('audioStudio.previewSource', { name: 'voice.wav' }))).toBeNull();
	});

	it('aborts and releases an in-flight transcription immediately when its source assets leaf is revoked', async () => {
		const pending = Promise.withResolvers<typeof timed>();
		calls.transcribe.mockReturnValueOnce(pending.promise);
		render(AudioStudio);
		await openStt();
		await chooseAudio(new File(['audio'], 'voice.wav', { type: 'audio/wav' }));
		const source = screen.getByLabelText(t('audioStudio.previewSource', { name: 'voice.wav' })).getAttribute('src');
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.convertToText') }));
		const signal: AbortSignal = calls.transcribe.mock.calls[0][3];
		grantLumen('lumen-audio_user');
		await waitFor(() => expect(signal.aborted).toBe(true));
		expect(URL.revokeObjectURL).toHaveBeenCalledWith(source);
		expect(screen.queryByText(t('audioStudio.processingAudio'))).toBeNull();
		pending.resolve(timed);
		await pending.promise;
		expect(screen.queryByRole('link', { name: t('audioStudio.downloadText') })).toBeNull();
	});
	it('translates the active audio flow without changing language, native model IDs or transcript handoff', async () => {
		render(AudioStudio);
		await openStt();
		await chooseAudio(new File(['FAKE-WAV'], 'voice.wav', { type: 'audio/wav' }));
		await fireEvent.input(screen.getByLabelText(t('audioStudio.languageCode')), { target: { value: 'ja' } });
		initLocale('en');
		await screen.findByRole('tab', { name: t('audioStudio.speechToText') });
		expect((screen.getByLabelText(t('audioStudio.languageCode')) as HTMLInputElement).value).toBe('ja');
		expect((screen.getByRole('switch', { name: t('audioStudio.timestamps') }) as HTMLInputElement).checked).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.convertToText') }));
		await screen.findByText('둘째 문장');
		expect(calls.transcribe.mock.calls[0][0]).toEqual({ model_id: '19', input_asset_id: 'scanned-asset', language: 'ja', timestamp_granularities: ['segment'] });
		const srt = screen.getByRole('link', { name: t('audioStudio.downloadSrt') });
		expect(await readBlob(blobAt(srt.getAttribute('href')))).toContain('00:00:01,200 --> 00:00:03,800\n인식된 문장');
		await fireEvent.click(screen.getByRole('button', { name: t('audioStudio.insertIntoChat') }));
		expect(takeAudioTranscript('owner', 'project-1')).toBe(timed.text);
	});

	it('announces speech generation only while the request is in flight', async () => {
		const pending = Promise.withResolvers<Blob>();
		calls.speech.mockReturnValueOnce(pending.promise);
		render(AudioStudio);
		await screen.findByText('음성 생성 경로와 가격이 준비되었습니다.');
		await fireEvent.input(screen.getByRole('textbox', { name: /읽을 텍스트/ }), { target: { value: 'Hello' } });
		await fireEvent.click(screen.getByRole('button', { name: '음성 생성' }));
		expect(screen.getAllByRole('status').some((status) => status.textContent?.trim() === t('audioStudio.speechGenerating'))).toBe(true);
		pending.resolve(new Blob(['audio'], { type: 'audio/mpeg' }));
		await screen.findByRole('link', { name: '음성 다운로드' });
		expect(screen.getAllByRole('status').some((status) => status.textContent?.trim() === t('audioStudio.speechGenerating'))).toBe(false);
	});

	it('plays real Blob bytes, keeps them across mode switches, reuses an ambiguous speech intent and revokes playback on owner switch', async () => {
		calls.speech.mockRejectedValueOnce(new Error('lost response'));
		const view = render(AudioStudio);
		await screen.findByText('음성 생성 경로와 가격이 준비되었습니다.');
		await fireEvent.input(screen.getByRole('textbox', { name: /읽을 텍스트/ }), { target: { value: 'Hello world' } });
		await fireEvent.click(screen.getByRole('radio', { name: 'nova' }));
		await fireEvent.change(screen.getByLabelText('출력 형식'), { target: { value: 'wav' } });
		await fireEvent.click(screen.getByRole('button', { name: '음성 생성' }));
		await screen.findByText('lost response');
		await fireEvent.click(screen.getByRole('button', { name: '음성 생성' }));
		const link = await screen.findByRole('link', { name: '음성 다운로드' });
		const speechUrl = link.getAttribute('href');
		expect(blobAt(speechUrl).size).toBe(16);
		expect(link.getAttribute('download')).toBe('speech.wav');
		expect(screen.getByLabelText('생성된 음성').getAttribute('src')).toBe(speechUrl);
		expect(calls.speech.mock.calls[0][0]).toMatchObject({ model_id: '17', input: 'Hello world', voice: 'nova', response_format: 'wav' });
		expect(calls.speech.mock.calls[1][2]).toBe(calls.speech.mock.calls[0][2]);
		expect(calls.speech.mock.calls[1][2]).toMatch(/^[0-9a-f-]{36}$/);
		await fireEvent.click(screen.getByRole('tab', { name: '음성 → 텍스트' }));
		expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
		expect(screen.queryByRole('link', { name: '음성 다운로드' })).toBeNull();
		await fireEvent.click(screen.getByRole('tab', { name: '텍스트 → 음성' }));
		expect(screen.getByRole('link', { name: '음성 다운로드' }).getAttribute('href')).toBe(speechUrl);
		expect(URL.revokeObjectURL).not.toHaveBeenCalledWith(speechUrl);
		auth.set(user('project-2'));
		await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith(speechUrl));
		expect(screen.queryByRole('link', { name: '음성 다운로드' })).toBeNull();
		view.unmount();
	});

	it('uses the selected Gemini model voice and WAV-only format from capabilities', async () => {
		calls.models.mockImplementation(async (kind: 'tts' | 'stt') => kind === 'tts' ? [model('tts'), { ...model('tts'), id: 18, model_name: 'gemini-speech', display_name: 'Gemini speech' }] : [model('stt')]);
		calls.capabilities.mockImplementation(async (kind: 'tts' | 'stt', id: number) => kind === 'tts' && id === 18 ? { ...capability(kind, id), available_voices: ['Puck', 'Zephyr'], available_formats: ['wav'] } : capability(kind, id));
		render(AudioStudio);
		await screen.findByText('음성 생성 경로와 가격이 준비되었습니다.');
		await fireEvent.change(screen.getByLabelText('음성 모델'), { target: { value: '18' } });
		await waitFor(() => expect((screen.getByRole('radio', { name: 'Puck' }) as HTMLInputElement).checked).toBe(true));
		expect(screen.queryByRole('radio', { name: 'alloy' })).toBeNull();
		expect((screen.getByLabelText('출력 형식') as HTMLSelectElement).value).toBe('wav');
		expect(screen.getByRole('radio', { name: 'Zephyr' })).toBeTruthy();
		expect(screen.queryByRole('option', { name: 'MP3' })).toBeNull();
		await fireEvent.input(screen.getByRole('textbox', { name: /읽을 텍스트/ }), { target: { value: 'Hello Gemini' } });
		await fireEvent.click(screen.getByRole('button', { name: '음성 생성' }));
		await waitFor(() => expect(calls.speech).toHaveBeenCalledWith({ model_id: '18', input: 'Hello Gemini', voice: 'Puck', response_format: 'wav' }, { token: 'token', projectId: 'project-1' }, expect.any(String), expect.any(AbortSignal)));
	});

	it('example text only fills an empty draft', async () => {
		render(AudioStudio);
		await screen.findByText('음성 생성 경로와 가격이 준비되었습니다.');
		const draft = screen.getByRole('textbox', { name: /읽을 텍스트/ }) as HTMLTextAreaElement;
		await fireEvent.click(screen.getByRole('button', { name: '차분한 안내' }));
		expect(draft.value).toContain('회의를 시작하겠습니다');
		await fireEvent.input(draft, { target: { value: '내 원고' } });
		expect(screen.queryByRole('button', { name: '따뜻한 인사말' })).toBeNull();
		expect(draft.value).toBe('내 원고');
	});

	it('previews scanned audio, requests advertised segment timestamps, shows provider ranges and exports TXT/SRT', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		vi.stubGlobal('navigator', Object.assign(Object.create(navigator), { clipboard: { writeText } }));
		render(AudioStudio);
		await openStt();
		const file = new File(['FAKE-WAV'], '회의 샘플.final.wav', { type: 'audio/wav' });
		await chooseAudio(file);
		expect(calls.upload).toHaveBeenCalledWith(file, { token: 'token', projectId: 'project-1' }, expect.any(AbortSignal));
		const previewUrl = created.find((item) => item.blob === file)?.url;
		expect(screen.getByLabelText('선택한 음성 미리 듣기: 회의 샘플.final.wav').getAttribute('src')).toBe(previewUrl);
		expect((screen.getByRole('switch', { name: '타임스탬프' }) as HTMLInputElement).checked).toBe(true);
		await fireEvent.input(screen.getByLabelText('언어 코드 (선택)'), { target: { value: 'ko' } });
		calls.transcribe.mockRejectedValueOnce(new Error('lost transcription'));
		await fireEvent.click(screen.getByRole('button', { name: '텍스트로 변환' }));
		await screen.findByText('lost transcription');
		await fireEvent.click(screen.getByRole('button', { name: '텍스트로 변환' }));
		await screen.findByText('둘째 문장');
		expect(calls.transcribe.mock.calls[0][0]).toEqual({ model_id: '19', input_asset_id: 'scanned-asset', language: 'ko', timestamp_granularities: ['segment'] });
		expect(calls.transcribe.mock.calls[1][2]).toBe(calls.transcribe.mock.calls[0][2]);
		expect(calls.transcribe.mock.calls[1][2]).toMatch(/^[0-9a-f-]{36}$/);
		const first = within(screen.getAllByRole('row')[1]);
		expect(first.getByText('00:00:01.200')).toBeTruthy();
		expect(first.getByText('00:00:03.800')).toBeTruthy();
		expect(first.getByText('인식된 문장')).toBeTruthy();
		const txt = screen.getByRole('link', { name: '텍스트 다운로드' });
		const srt = screen.getByRole('link', { name: 'SRT 다운로드' });
		expect(txt.getAttribute('download')).toBe('회의_샘플.final.txt');
		expect(srt.getAttribute('download')).toBe('회의_샘플.final.srt');
		expect(blobAt(txt.getAttribute('href')).type).toBe('text/plain;charset=utf-8');
		const txtBody = await readBlob(blobAt(txt.getAttribute('href')));
		expect(txtBody).toContain('00:00:04.100');
		expect(txtBody).toContain('둘째 문장');
		const srtBody = await readBlob(blobAt(srt.getAttribute('href')));
		expect(srtBody).toContain('1\n00:00:01,200 --> 00:00:03,800\n인식된 문장');
		expect(srtBody).toContain('2\n00:00:04,100 --> 00:00:06,500\n둘째 문장');
		await fireEvent.click(screen.getByRole('button', { name: '텍스트 복사' }));
		expect(writeText).toHaveBeenCalledWith('인식된 문장 둘째 문장');
		await fireEvent.click(screen.getByRole('button', { name: '채팅 입력에 넣기' }));
		expect(calls.goto).toHaveBeenCalledWith('/dashboard/chat');
		expect(takeAudioTranscript('owner', 'project-1')).toBe('인식된 문장 둘째 문장');
		await fireEvent.click(screen.getByRole('button', { name: '선택한 음성 제거' }));
		for (const url of [previewUrl, txt.getAttribute('href'), srt.getAttribute('href')]) expect(URL.revokeObjectURL).toHaveBeenCalledWith(url);
		expect(screen.queryByRole('link', { name: 'SRT 다운로드' })).toBeNull();
		expect(screen.getByRole('button', { name: '텍스트로 변환' }).hasAttribute('disabled')).toBe(true);
	});

	it('treats timestamp choice as part of the transcription intent', async () => {
		calls.transcribe.mockRejectedValueOnce(new Error('lost transcription')).mockResolvedValueOnce({ text: '평문 결과', segments: [] });
		render(AudioStudio);
		await openStt();
		await chooseAudio(new File(['FAKE-WAV'], 'voice.wav', { type: 'audio/wav' }));
		await fireEvent.click(screen.getByRole('button', { name: '텍스트로 변환' }));
		await screen.findByText('lost transcription');
		await fireEvent.click(screen.getByRole('switch', { name: '타임스탬프' }));
		await fireEvent.click(screen.getByRole('button', { name: '텍스트로 변환' }));
		await screen.findByText('평문 결과');
		expect(calls.transcribe.mock.calls[0][0]).toHaveProperty('timestamp_granularities', ['segment']);
		expect(calls.transcribe.mock.calls[1][0]).not.toHaveProperty('timestamp_granularities');
		expect(calls.transcribe.mock.calls[1][2]).not.toBe(calls.transcribe.mock.calls[0][2]);
		expect(screen.queryByRole('link', { name: 'SRT 다운로드' })).toBeNull();
	});

	it('keeps models without timestamp support text-only with TXT export and no SRT', async () => {
		calls.capabilities.mockImplementation(async (kind: 'tts' | 'stt', id: number) => capability(kind, id, false));
		calls.transcribe.mockResolvedValueOnce({ text: '평문 결과', segments: [] });
		render(AudioStudio);
		await openStt();
		const toggle = screen.getByRole('switch', { name: '타임스탬프' }) as HTMLInputElement;
		expect(toggle.disabled).toBe(true);
		expect(toggle.checked).toBe(false);
		expect(screen.getByText(/구간 타임스탬프를 제공하지 않습니다/)).toBeTruthy();
		await chooseAudio(new File(['FAKE-WAV'], 'voice.wav', { type: 'audio/wav' }));
		await fireEvent.click(screen.getByRole('button', { name: '텍스트로 변환' }));
		await screen.findByText('평문 결과');
		expect(calls.transcribe.mock.calls[0][0]).toEqual({ model_id: '19', input_asset_id: 'scanned-asset' });
		const txt = screen.getByRole('link', { name: '텍스트 다운로드' });
		expect(txt.getAttribute('download')).toBe('voice.txt');
		expect(await readBlob(blobAt(txt.getAttribute('href')))).toBe('평문 결과');
		expect(screen.queryByRole('link', { name: 'SRT 다운로드' })).toBeNull();
		expect(screen.queryByRole('table')).toBeNull();
	});

	it('reports microphone denial without uploading or recording automatically', async () => {
		const getUserMedia = vi.fn().mockRejectedValue(new DOMException('denied', 'NotAllowedError'));
		vi.stubGlobal('navigator', Object.assign(Object.create(navigator), { mediaDevices: { getUserMedia } }));
		vi.stubGlobal('MediaRecorder', class {});
		render(AudioStudio);
		await openStt();
		expect(getUserMedia).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '마이크 녹음' }));
		await screen.findByText('마이크 권한이 거부되었습니다. 브라우저 권한을 확인하거나 파일을 선택하세요.');
		expect(calls.upload).not.toHaveBeenCalled();
	});

	it('records only after permission, holds the STT mode while capturing, and uploads recorded bytes as a scanned asset', async () => {
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
		await openStt();
		await fireEvent.click(screen.getByRole('button', { name: '마이크 녹음' }));
		await screen.findByText('녹음 중 · 종료하면 업로드합니다.');
		const ttsTab = screen.getByRole('tab', { name: '텍스트 → 음성' });
		expect(ttsTab.hasAttribute('disabled')).toBe(true);
		await fireEvent.click(ttsTab);
		expect(screen.getByRole('button', { name: '녹음 종료' })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '녹음 종료' }));
		await waitFor(() => expect(calls.upload).toHaveBeenCalled());
		const file: File = calls.upload.mock.calls[0][0];
		expect(file.type).toBe('audio/webm');
		expect(file.size).toBe(14);
		expect(file.name).toBe('recording.webm');
		expect(stop).toHaveBeenCalled();
		expect(screen.getByRole('tab', { name: '텍스트 → 음성' }).hasAttribute('disabled')).toBe(false);
	});

	it('releases the microphone without uploading and revokes every object URL on unmount', async () => {
		const stop = vi.fn();
		vi.stubGlobal('navigator', Object.assign(Object.create(navigator), { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }) } }));
		vi.stubGlobal('MediaRecorder', class {
			static isTypeSupported = () => true;
			mimeType = 'audio/webm';
			state = 'inactive';
			ondataavailable: ((event: { data: Blob }) => void) | null = null;
			onstop: (() => void) | null = null;
			start() { this.state = 'recording'; }
			stop() { this.ondataavailable?.({ data: new Blob(['late bytes']) }); this.state = 'inactive'; this.onstop?.(); }
		});
		const view = render(AudioStudio);
		await screen.findByText('음성 생성 경로와 가격이 준비되었습니다.');
		await fireEvent.input(screen.getByRole('textbox', { name: /읽을 텍스트/ }), { target: { value: 'Hello' } });
		await fireEvent.click(screen.getByRole('button', { name: '음성 생성' }));
		await screen.findByRole('link', { name: '음성 다운로드' });
		await openStt();
		await chooseAudio(new File(['FAKE-WAV'], 'voice.wav', { type: 'audio/wav' }));
		await fireEvent.click(screen.getByRole('button', { name: '텍스트로 변환' }));
		await screen.findByRole('link', { name: 'SRT 다운로드' });
		await fireEvent.click(screen.getByRole('button', { name: '마이크 녹음' }));
		await screen.findByText('녹음 중 · 종료하면 업로드합니다.');
		const uploads = calls.upload.mock.calls.length;
		view.unmount();
		expect(stop).toHaveBeenCalled();
		expect(calls.upload).toHaveBeenCalledTimes(uploads);
		expect(created).toHaveLength(4);
		for (const { url } of created) expect(URL.revokeObjectURL).toHaveBeenCalledWith(url);
	});

	it('refuses unpriced and unsupported routes, and drops stale asset and transcription responses on project change', async () => {
		calls.models.mockImplementation(async (kind: 'tts' | 'stt') => [model(kind, false)]);
		render(AudioStudio);
		await screen.findAllByText('오디오 가격이 설정되지 않았습니다.');
		await fireEvent.input(screen.getByRole('textbox', { name: /읽을 텍스트/ }), { target: { value: 'not charged' } });
		expect(screen.getByRole('button', { name: '음성 생성' }).hasAttribute('disabled')).toBe(true);
		expect(calls.speech).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('tab', { name: '음성 → 텍스트' }));
		await screen.findAllByText('오디오 가격이 설정되지 않았습니다.');
		const { promise, resolve } = Promise.withResolvers<{ id: string; name: string }>();
		calls.upload.mockImplementationOnce(() => promise);
		await fireEvent.change(screen.getByLabelText('음성 파일 선택'), { target: { files: [new File(['abc'], 'first.wav', { type: 'audio/wav' })] } });
		expect(screen.getAllByRole('status').some((status) => status.textContent?.trim() === '업로드하고 검사하는 중…')).toBe(true);
		auth.set(user('project-2'));
		resolve({ id: 'old-asset', name: 'first.wav' });
		await waitFor(() => expect(calls.models).toHaveBeenCalledWith('stt', { token: 'token', projectId: 'project-2' }));
		expect(screen.queryByText('검사된 입력: first.wav')).toBeNull();
		expect(screen.queryByText('first.wav')).toBeNull();
		expect(screen.queryByText('업로드하고 검사하는 중…')).toBeNull();
	});

	it('ignores a transcription that resolves after the project changes', async () => {
		const pending = Promise.withResolvers<typeof timed>();
		calls.transcribe.mockImplementationOnce(() => pending.promise);
		render(AudioStudio);
		await openStt();
		await chooseAudio(new File(['FAKE-WAV'], 'voice.wav', { type: 'audio/wav' }));
		await fireEvent.click(screen.getByRole('button', { name: '텍스트로 변환' }));
		expect(screen.getAllByRole('status').some((status) => status.textContent?.trim() === '음성 처리 중…')).toBe(true);
		const signal: AbortSignal = calls.transcribe.mock.calls[0][3];
		auth.set(user('project-2'));
		await waitFor(() => expect(signal.aborted).toBe(true));
		pending.resolve(timed);
		await waitFor(() => expect(calls.models).toHaveBeenCalledWith('stt', { token: 'token', projectId: 'project-2' }));
		expect(screen.queryByText('둘째 문장')).toBeNull();
		expect(screen.queryByRole('link', { name: '텍스트 다운로드' })).toBeNull();
		expect(screen.getAllByRole('status').some((status) => status.textContent?.trim() === '음성 처리 중…')).toBe(false);
	});
});
