import { grantLumen, pendingLumen } from './lumenPermissionFixture';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import type * as ImageStudioModule from '$lib/api/imageStudio';
import { ApiError } from '$lib/api/client';
import ImageStudio from '../ImageStudio.svelte';
import { IMAGE_STUDIO_STYLES, imageRequestAspectRatio } from '../imageStudioStyles';
import { t } from '$lib/i18n/ns/chat-studio';
import { initLocale } from '$lib/i18n/runtime.svelte';

const api = vi.hoisted(() => ({
	models: vi.fn(), capabilities: vi.fn(), submit: vi.fn(), run: vi.fn(), cancel: vi.fn(), upload: vi.fn(), download: vi.fn()
}));
vi.mock('$lib/api/client', () => ({
	ApiError: class ApiError extends Error {
		constructor(public status: number, message: string) { super(message); }
	},
	api: { get: vi.fn() },
	fetchWithAuth: vi.fn()
}));
vi.mock('$lib/api/imageStudio', async (original) => ({
	...await original<typeof ImageStudioModule>(),
	imageStudioApi: api
}));
const ready = {
	id: 1, model_name: 'image-model', display_name: 'Image Model', provider_api_key_configured: true,
	capabilities: { feature_gates: { image_output: { available: true, mode: 'native', pricing_available: true, reason_code: null } } }
};
const owner = {
	token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'user-1', username: 'tester',
	projectId: 'project-1', projectName: 'Project 1', availableProjects: [], roles: [], isSystemAdmin: false, federated: false
};

beforeEach(() => {
	vi.clearAllMocks();
	sessionStorage.clear();
	auth.set(owner);
	api.models.mockResolvedValue([ready]);
	api.capabilities.mockResolvedValue({ available_image_variants: ['1024x1024:high', '1024x1024:medium'], max_image_count: 4 });
	api.submit.mockResolvedValue({ run_id: 'run-1', status: 'queued' });
	api.run.mockResolvedValue({ run_id: 'run-1', status: 'completed', terminal: true, output_assets: [{ asset_id: 'asset-1', size_bytes: 5, download_url: '/v1/assets/asset-1/download', mime_type: 'image/png' }] });
	api.cancel.mockResolvedValue({});
	api.upload.mockResolvedValue({ id: 'input-1', name: 'source.png', mime_type: 'image/png' });
	api.download.mockResolvedValue(new Blob(['image'], { type: 'image/png' }));
	const OriginalURL = URL;
	vi.stubGlobal('URL', Object.assign(class extends OriginalURL {}, {
		createObjectURL: vi.fn(() => 'blob:preview'), revokeObjectURL: vi.fn()
	}));
});
afterEach(() => { cleanup(); initLocale('ko'); vi.unstubAllGlobals(); });

describe('Image Studio', () => {
	it('denies image generation to a chat-only user on the direct studio route', async () => {
		grantLumen('lumen-chat_user');
		render(ImageStudio);
		expect(screen.getByRole('button', { name: t('imageStudio.createImage') }).hasAttribute('disabled')).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('imageStudio.createImage') }));
		expect(api.submit).not.toHaveBeenCalled();
	});
	it.each(['', 'permission lookup failed'])('preserves input, output and selected options through same-actor refresh (%s)', async (permissionError) => {
		let sequence = 0;
		vi.mocked(URL.createObjectURL).mockImplementation(() => `blob:preserved-${++sequence}`);
		render(ImageStudio);
		await screen.findByRole('option', { name: t('imageStudio.quality.high') });
		await fireEvent.input(screen.getByRole('textbox', { name: t('imageStudio.prompt') }), { target: { value: 'Keep this composition' } });
		await fireEvent.change(screen.getByRole('combobox', { name: t('imageStudio.qualityLabel') }), { target: { value: 'medium' } });
		await fireEvent.change(screen.getByRole('combobox', { name: t('imageStudio.imageCount') }), { target: { value: '2' } });
		await fireEvent.change(screen.getByLabelText(t('imageStudio.inputImage')), { target: { files: [new File(['pixels'], 'source.png', { type: 'image/png' })] } });
		await screen.findByText(t('imageStudio.uploadComplete', { name: 'source.png' }));
		const input = screen.getByRole('img', { name: t('imageStudio.inputPreview') }).getAttribute('src');
		await fireEvent.click(screen.getByRole('button', { name: t('imageStudio.createImage') }));
		const output = (await screen.findByRole('img', { name: t('imageStudio.generatedImage') })).getAttribute('src');
		pendingLumen(permissionError);
		auth.set({ ...owner, token: 'refreshed-token' });
		await waitFor(() => expect(screen.getByRole('button', { name: t('imageStudio.createImage') }).hasAttribute('disabled')).toBe(true));
		expect(screen.getByLabelText(t('imageStudio.inputImage')).hasAttribute('disabled')).toBe(true);
		expect(screen.getByRole('combobox', { name: t('imageStudio.size') }).hasAttribute('disabled')).toBe(true);
		expect(screen.queryByRole('img', { name: t('imageStudio.generatedImage') })).toBeNull();
		expect(screen.queryByRole('img', { name: t('imageStudio.inputPreview') })).toBeNull();
		expect(URL.revokeObjectURL).not.toHaveBeenCalled();
		await fireEvent.submit(screen.getByRole('form', { name: t('imageStudio.request') }));
		await fireEvent.change(screen.getByLabelText(t('imageStudio.inputImage')), { target: { files: [new File(['other'], 'other.png', { type: 'image/png' })] } });
		expect(api.submit).toHaveBeenCalledTimes(1);
		expect(api.upload).toHaveBeenCalledTimes(1);
		grantLumen('lumen-images_user', 'lumen-assets_editor');
		expect((await screen.findByRole('img', { name: t('imageStudio.generatedImage') })).getAttribute('src')).toBe(output);
		expect(screen.getByRole('img', { name: t('imageStudio.inputPreview') }).getAttribute('src')).toBe(input);
		expect((screen.getByRole('textbox', { name: t('imageStudio.prompt') }) as HTMLTextAreaElement).value).toBe('Keep this composition');
		expect((screen.getByRole('combobox', { name: t('imageStudio.qualityLabel') }) as HTMLSelectElement).value).toBe('medium');
		expect((screen.getByRole('combobox', { name: t('imageStudio.imageCount') }) as HTMLSelectElement).value).toBe('2');
		expect(api.models).toHaveBeenCalledTimes(1);
		expect(api.capabilities).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: t('imageStudio.createImage') }));
		await waitFor(() => expect(api.submit).toHaveBeenLastCalledWith('edits', expect.objectContaining({ input_asset_id: 'input-1', quality: 'medium', n: 2 }), { token: 'refreshed-token', projectId: 'project-1' }, expect.any(String), expect.any(AbortSignal)));
	});

	it('keeps an upload alive through token refresh and publishes only after current assets permission returns', async () => {
		const upload = Promise.withResolvers<{ id: string; name: string }>();
		api.upload.mockReturnValueOnce(upload.promise);
		render(ImageStudio);
		await screen.findByRole('option', { name: t('imageStudio.quality.high') });
		await fireEvent.change(screen.getByLabelText(t('imageStudio.inputImage')), { target: { files: [new File(['pixels'], 'source.png', { type: 'image/png' })] } });
		const signal: AbortSignal = api.upload.mock.calls[0][2];
		pendingLumen();
		auth.set({ ...owner, token: 'refreshed-token' });
		await waitFor(() => expect(screen.getByLabelText(t('imageStudio.inputImage')).hasAttribute('disabled')).toBe(true));
		expect(signal.aborted).toBe(false);
		expect(URL.revokeObjectURL).not.toHaveBeenCalled();
		grantLumen('lumen-images_user', 'lumen-assets_editor');
		upload.resolve({ id: 'input-1', name: 'source.png' });
		await screen.findByText(t('imageStudio.uploadComplete', { name: 'source.png' }));
	});

	it('does not publish a response settled during pending permissions and retains its retry intent', async () => {
		const admission = Promise.withResolvers<{ run_id: string; status: string }>();
		api.submit.mockReturnValueOnce(admission.promise);
		render(ImageStudio);
		await screen.findByRole('option', { name: t('imageStudio.quality.high') });
		await fireEvent.input(screen.getByRole('textbox', { name: t('imageStudio.prompt') }), { target: { value: 'sunset' } });
		await fireEvent.click(screen.getByRole('button', { name: t('imageStudio.createImage') }));
		pendingLumen();
		admission.resolve({ run_id: 'unpublished-run', status: 'queued' });
		await admission.promise;
		await screen.findByRole('button', { name: t('imageStudio.createImage') });
		expect(screen.queryByRole('img', { name: t('imageStudio.generatedImage') })).toBeNull();
		expect(sessionStorage.getItem('afterglow:image-studio:user-1:project-1')).toBeNull();
		grantLumen('lumen-images_user', 'lumen-assets_editor');
		await waitFor(() => expect(screen.getByRole('button', { name: t('imageStudio.createImage') }).hasAttribute('disabled')).toBe(false));
		expect(screen.queryByRole('img', { name: t('imageStudio.generatedImage') })).toBeNull();
		expect((screen.getByRole('textbox', { name: t('imageStudio.prompt') }) as HTMLTextAreaElement).value).toBe('sunset');
		api.submit.mockResolvedValueOnce({ run_id: 'unpublished-run', status: 'queued' });
		await fireEvent.click(screen.getByRole('button', { name: t('imageStudio.createImage') }));
		await screen.findByRole('img', { name: t('imageStudio.generatedImage') });
		expect(api.submit.mock.calls[1][3]).toBe(api.submit.mock.calls[0][3]);
		expect(sessionStorage.getItem('afterglow:image-studio:user-1:project-1')).toContain('unpublished-run');
	});

	it('pauses active run polling while pending and resumes with the refreshed token', async () => {
		api.run.mockResolvedValue({ run_id: 'run-1', status: 'running', terminal: false, output_assets: [] });
		const view = render(ImageStudio);
		try {
			await screen.findByRole('option', { name: t('imageStudio.quality.high') });
			await fireEvent.input(screen.getByRole('textbox', { name: t('imageStudio.prompt') }), { target: { value: 'sunset' } });
			vi.useFakeTimers();
			await fireEvent.click(screen.getByRole('button', { name: t('imageStudio.createImage') }));
			await vi.advanceTimersByTimeAsync(0);
			expect(api.run).toHaveBeenCalledTimes(1);
			pendingLumen();
			auth.set({ ...owner, token: 'refreshed-token' });
			await vi.advanceTimersByTimeAsync(6000);
			expect(api.run).toHaveBeenCalledTimes(1);
			expect(screen.queryByLabelText(t('imageStudio.developing'))).toBeNull();
			grantLumen('lumen-images_user', 'lumen-assets_editor');
			await vi.advanceTimersByTimeAsync(0);
			expect(api.run).toHaveBeenLastCalledWith('run-1', { token: 'refreshed-token', projectId: 'project-1' });
			expect(screen.getByLabelText(t('imageStudio.developing'))).toBeTruthy();
		} finally { view.unmount(); vi.useRealTimers(); }
	});

	it.each(['project', 'user', 'logout', 'switching'] as const)('clears input and output on actual %s transition', async (transition) => {
		render(ImageStudio);
		await screen.findByRole('option', { name: t('imageStudio.quality.high') });
		await fireEvent.input(screen.getByRole('textbox', { name: t('imageStudio.prompt') }), { target: { value: 'sunset' } });
		await fireEvent.change(screen.getByLabelText(t('imageStudio.inputImage')), { target: { files: [new File(['pixels'], 'source.png', { type: 'image/png' })] } });
		await screen.findByText(t('imageStudio.uploadComplete', { name: 'source.png' }));
		await fireEvent.click(screen.getByRole('button', { name: t('imageStudio.createImage') }));
		await screen.findByRole('img', { name: t('imageStudio.generatedImage') });
		if (transition === 'project') auth.set({ ...owner, projectId: 'project-2' });
		else if (transition === 'user') auth.set({ ...owner, userId: 'another-user' });
		else if (transition === 'logout') authReady.set(false);
		else projectSwitching.set(true);
		await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2));
		expect(screen.queryByRole('img', { name: t('imageStudio.generatedImage') })).toBeNull();
		expect(screen.queryByRole('img', { name: t('imageStudio.inputPreview') })).toBeNull();
		expect(screen.queryByRole('button', { name: /run-1/ })).toBeNull();
	});

	it.each(['lumen-images_user', 'lumen-assets_editor'])('releases only the state owned by the definitively revoked %s leaf', async (revoked) => {
		let sequence = 0;
		vi.mocked(URL.createObjectURL).mockImplementation(() => `blob:revocation-${++sequence}`);
		render(ImageStudio);
		await screen.findByRole('option', { name: t('imageStudio.quality.high') });
		await fireEvent.input(screen.getByRole('textbox', { name: t('imageStudio.prompt') }), { target: { value: 'sunset' } });
		await fireEvent.change(screen.getByLabelText(t('imageStudio.inputImage')), { target: { files: [new File(['pixels'], 'source.png', { type: 'image/png' })] } });
		await screen.findByText(t('imageStudio.uploadComplete', { name: 'source.png' }));
		const input = screen.getByRole('img', { name: t('imageStudio.inputPreview') }).getAttribute('src');
		await fireEvent.click(screen.getByRole('button', { name: t('imageStudio.createImage') }));
		const output = (await screen.findByRole('img', { name: t('imageStudio.generatedImage') })).getAttribute('src');
		if (revoked === 'lumen-images_user') {
			grantLumen('lumen-assets_editor');
			await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith(output));
			expect(URL.revokeObjectURL).not.toHaveBeenCalledWith(input);
			expect(screen.getByRole('img', { name: t('imageStudio.inputPreview') })).toBeTruthy();
			expect(screen.getByRole('button', { name: t('imageStudio.replaceImage') }).hasAttribute('disabled')).toBe(false);
		} else {
			grantLumen('lumen-images_user');
			await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith(input));
			expect(URL.revokeObjectURL).not.toHaveBeenCalledWith(output);
			expect(screen.getByRole('img', { name: t('imageStudio.generatedImage') })).toBeTruthy();
			expect(screen.getByLabelText(t('imageStudio.inputImage')).hasAttribute('disabled')).toBe(true);
		}
	});
	it.each(['en', 'ja', 'zh-CN'] as const)('translates style controls in %s without changing the provider prompt or retry intent', async (locale) => {
		api.submit.mockRejectedValue(new Error('lost response'));
		const style = IMAGE_STUDIO_STYLES.find((candidate) => candidate.id === 'cinematic')!;
		render(ImageStudio);
		await screen.findByRole('option', { name: 'Image Model' });
		await fireEvent.input(screen.getByRole('textbox', { name: t('imageStudio.prompt') }), { target: { value: 'My unchanged draft' } });
		await fireEvent.click(screen.getByRole('button', { name: t(style.labelKey) }));
		await fireEvent.click(screen.getByRole('button', { name: t('imageStudio.createImage') }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(1));
		await waitFor(() => expect((screen.getByRole('button', { name: t('imageStudio.createImage') }) as HTMLButtonElement).disabled).toBe(false));
		const first = api.submit.mock.calls[0];
		initLocale(locale);
		const translatedStyle = await screen.findByRole('button', { name: t(style.labelKey) });
		expect(translatedStyle.getAttribute('aria-pressed')).toBe('true');
		expect(document.getElementById('studio-style-note')?.textContent).toContain(first[1].prompt.slice('My unchanged draft\n\n'.length));
		expect((screen.getByRole('textbox', { name: t('imageStudio.prompt') }) as HTMLTextAreaElement).value).toBe('My unchanged draft');
		expect((screen.getByRole('combobox', { name: t('imageStudio.qualityLabel') }) as HTMLSelectElement).value).toBe('high');
		await fireEvent.click(screen.getByRole('button', { name: t('imageStudio.createImage') }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(2));
		expect(api.submit.mock.calls[1][1]).toEqual({ model_id: '1', prompt: `My unchanged draft\n\n스타일: ${style.instruction}`, size: '1024x1024', quality: 'high', n: 1 });
		expect(api.submit.mock.calls[1][3]).toBe(first[3]);
	});

	it('updates local elapsed time and does not replay completion on a pending status poll', async () => {
		api.run.mockResolvedValue({ run_id: 'run-1', status: 'waiting_resource', terminal: false, output_assets: [] });
		const view = render(ImageStudio);
		try {
			await screen.findByRole('option', { name: t('imageStudio.quality.high') });
			await fireEvent.input(screen.getByRole('textbox', { name: t('imageStudio.prompt') }), { target: { value: 'orange dusk' } });
			vi.useFakeTimers();
			vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
			await fireEvent.click(screen.getByRole('button', { name: t('imageStudio.createImage') }));
			await vi.advanceTimersByTimeAsync(0);
			const developing = screen.getByLabelText(t('imageStudio.developing'));
			expect(developing.textContent).toContain(t('imageStudio.status.waitingResource'));
			await vi.advanceTimersByTimeAsync(3000);
			expect(developing.textContent).toContain(t('imageStudio.elapsedSinceRequest', { seconds: 3 }));
			expect(screen.getByLabelText(t('imageStudio.developing'))).toBe(developing);
			// Cancellation can race completion; the resulting status read is still a live completion.
			api.run.mockResolvedValue({ run_id: 'run-1', status: 'completed', terminal: true, output_assets: [{ asset_id: 'asset-1', mime_type: 'image/png', size_bytes: 5, download_url: '/asset-1' }] });
			await fireEvent.click(screen.getByRole('button', { name: t('imageStudio.cancelJob') }));
			await vi.advanceTimersByTimeAsync(0);
			const image = screen.getByRole('img', { name: t('imageStudio.generatedImage') });
			expect(image.classList.contains('motion-pop')).toBe(true);
			await vi.advanceTimersByTimeAsync(1000);
			expect(api.run).toHaveBeenCalledTimes(4);
			expect(screen.getByRole('img', { name: t('imageStudio.generatedImage') })).toBe(image);
			expect(api.download).toHaveBeenCalledTimes(1);
		} finally {
			view.unmount();
			vi.useRealTimers();
		}
	});

	it('blocks submission when image route or pricing is unavailable even if a model is listed', async () => {
		api.models.mockResolvedValue([{ ...ready, capabilities: { feature_gates: { image_output: { available: false, mode: 'none', pricing_available: false, reason_code: 'route_unavailable' } } } }]);
		render(ImageStudio);
		await screen.findByText(/route_unavailable/);
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'orange dusk' } });
		expect((screen.getByRole('button', { name: '이미지 만들기' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.submit).not.toHaveBeenCalled();
	});

	it('rejects an unpriced model variant and never submits a guessed default', async () => {
		api.capabilities.mockResolvedValue({ available_image_variants: [], max_image_count: 0 });
		render(ImageStudio);
		await screen.findByText('선택한 모델의 가격이 설정된 이미지 크기·품질을 사용할 수 없습니다.');
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'orange dusk' } });
		expect((screen.getByRole('button', { name: '이미지 만들기' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.submit).not.toHaveBeenCalled();
	});

	it('explains an empty image model catalog and keeps submission disabled', async () => {
		api.models.mockResolvedValue([]);
		render(ImageStudio);
		await screen.findByText('사용 가능한 이미지 모델 없음');
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'orange dusk' } });
		expect((screen.getByRole('button', { name: '이미지 만들기' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.capabilities).not.toHaveBeenCalled();
	});

	it('submits a ready generation, displays owned output and restores it from local history', async () => {
		const mounted = render(ImageStudio);
		await screen.findByRole('option', { name: 'Image Model' });
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'orange dusk' } });
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledWith('generations', expect.objectContaining({ model_id: '1', prompt: 'orange dusk', size: '1024x1024', quality: 'high', n: 1 }), { token: 'token', projectId: 'project-1' }, expect.any(String), expect.any(AbortSignal)));
		const liveImage = await screen.findByRole('img', { name: '생성된 이미지' });
		expect(liveImage.classList.contains('motion-pop')).toBe(true);
		expect(api.download).toHaveBeenCalledWith('asset-1', { token: 'token', projectId: 'project-1' }, expect.anything());
		mounted.unmount();
		render(ImageStudio);
		const historicalImage = await screen.findByRole('img', { name: '생성된 이미지' });
		expect(historicalImage.classList.contains('motion-pop')).toBe(false);
		expect(api.run).toHaveBeenCalledWith('run-1', { token: 'token', projectId: 'project-1' });
	});

	it('does not animate an already completed admission replay', async () => {
		api.submit.mockResolvedValueOnce({ run_id: 'run-1', status: 'completed' });
		render(ImageStudio);
		await screen.findByRole('option', { name: 'high' });
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'orange dusk' } });
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		const replayedImage = await screen.findByRole('img', { name: '생성된 이미지' });
		expect(replayedImage.classList.contains('motion-pop')).toBe(false);
	});

	it('does not replay the live entrance when the same result is selected from history', async () => {
		render(ImageStudio);
		await screen.findByRole('option', { name: 'high' });
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'orange dusk' } });
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		await screen.findByRole('img', { name: '생성된 이미지' });
		await fireEvent.click(screen.getByRole('button', { name: /run-1/ }));
		const selectedImage = await screen.findByRole('img', { name: '생성된 이미지' });
		expect(selectedImage.classList.contains('motion-pop')).toBe(false);
	});

	it('uploads input without a mode choice and isolates input and history across projects', async () => {
		render(ImageStudio);
		await screen.findByRole('option', { name: 'high' });
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'make it warmer' } });
		await fireEvent.change(screen.getByLabelText('입력 이미지'), { target: { files: [new File(['pixels'], 'source.png', { type: 'image/png' })] } });
		await screen.findByText('업로드 완료: source.png');
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledWith('edits', expect.objectContaining({ model_id: '1', input_asset_id: 'input-1' }), { token: 'token', projectId: 'project-1' }, expect.any(String), expect.any(AbortSignal)));
		await screen.findByRole('img', { name: '생성된 이미지' });
		auth.set({ ...owner, projectId: 'project-2' });
		await waitFor(() => expect(screen.queryByRole('img', { name: '생성된 이미지' })).toBeNull());
		expect(screen.queryByRole('button', { name: /run-1/ })).toBeNull();
		expect(screen.queryByRole('img', { name: '입력 이미지 미리보기' })).toBeNull();
		await waitFor(() => expect((screen.getByRole('button', { name: '이미지 만들기' }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		await waitFor(() => expect(api.submit).toHaveBeenLastCalledWith('generations', expect.not.objectContaining({ input_asset_id: expect.anything() }), { token: 'token', projectId: 'project-2' }, expect.any(String), expect.any(AbortSignal)));
	});

	it('appends the visible style instruction to the submitted prompt and starts a new intent when the style changes or clears', async () => {
		const cinematic = IMAGE_STUDIO_STYLES.find((style) => style.id === 'cinematic')!;
		const pixel = IMAGE_STUDIO_STYLES.find((style) => style.id === 'pixel-art')!;
		api.submit.mockRejectedValueOnce(new Error('lost')).mockRejectedValueOnce(new Error('lost')).mockRejectedValueOnce(new Error('lost'));
		render(ImageStudio);
		await screen.findByRole('option', { name: 'high' });
		const promptBox = screen.getByRole('textbox', { name: /프롬프트/ }) as HTMLTextAreaElement;
		await fireEvent.input(promptBox, { target: { value: 'orange dusk' } });
		await fireEvent.click(screen.getByRole('button', { name: t(cinematic.labelKey) }));
		expect(screen.getByRole('button', { name: t(cinematic.labelKey) }).getAttribute('aria-pressed')).toBe('true');
		expect(promptBox.value).toBe('orange dusk');
		expect(screen.getByText(new RegExp(cinematic.instruction))).toBeTruthy();
		const submitButton = () => screen.getByRole('button', { name: '이미지 만들기' }) as HTMLButtonElement;
		await fireEvent.click(submitButton());
		await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(1));
		expect(api.submit.mock.calls[0][1]).toEqual(expect.objectContaining({ prompt: `orange dusk\n\n스타일: ${cinematic.instruction}` }));
		expect(api.submit.mock.calls[0][1]).not.toHaveProperty('style');
		await waitFor(() => expect(submitButton().disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: t(pixel.labelKey) }));
		expect(screen.getByRole('button', { name: t(cinematic.labelKey) }).getAttribute('aria-pressed')).toBe('false');
		await fireEvent.click(submitButton());
		await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(2));
		expect(api.submit.mock.calls[1][1].prompt).toBe(`orange dusk\n\n스타일: ${pixel.instruction}`);
		expect(api.submit.mock.calls[1][3]).not.toBe(api.submit.mock.calls[0][3]);
		await waitFor(() => expect(submitButton().disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: '스타일 지우기' }));
		expect(promptBox.value).toBe('orange dusk');
		await fireEvent.click(submitButton());
		await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(3));
		expect(api.submit.mock.calls[2][1].prompt).toBe('orange dusk');
		expect(new Set(api.submit.mock.calls.map((call) => call[3])).size).toBe(3);
	});

	it('previews the attached input and revokes it on replace, removal and unmount', async () => {
		let created = 0;
		vi.mocked(URL.createObjectURL).mockImplementation(() => `blob:input-${++created}`);
		api.upload.mockImplementation(async (file: File) => ({ id: `asset-${file.name}`, name: file.name, mime_type: 'image/png' }));
		const mounted = render(ImageStudio);
		await screen.findByRole('option', { name: 'Image Model' });
		const fileInput = screen.getByLabelText('입력 이미지');
		await fireEvent.change(fileInput, { target: { files: [new File(['a'], 'first.png', { type: 'image/png' })] } });
		expect((await screen.findByRole('img', { name: '입력 이미지 미리보기' })).getAttribute('src')).toBe('blob:input-1');
		await screen.findByText('업로드 완료: first.png');
		await fireEvent.change(fileInput, { target: { files: [new File(['b'], 'second.png', { type: 'image/png' })] } });
		await screen.findByText('업로드 완료: second.png');
		expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:input-1');
		expect(screen.getByRole('img', { name: '입력 이미지 미리보기' }).getAttribute('src')).toBe('blob:input-2');
		await fireEvent.click(screen.getByRole('button', { name: '첨부 이미지 제거' }));
		expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:input-2');
		expect(screen.queryByRole('img', { name: '입력 이미지 미리보기' })).toBeNull();
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'warmer' } });
		expect((screen.getByRole('button', { name: '이미지 만들기' }) as HTMLButtonElement).disabled).toBe(false);
		await fireEvent.change(fileInput, { target: { files: [new File(['c'], 'third.png', { type: 'image/png' })] } });
		await screen.findByText('업로드 완료: third.png');
		mounted.unmount();
		expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:input-3');
	});

	it('keeps an in-flight canonical input when a history run is selected during upload', async () => {
		sessionStorage.setItem('afterglow:image-studio:user-1:project-1', JSON.stringify(['run-1', 'run-2']));
		const upload = Promise.withResolvers<{ id: string; name: string; mime_type: string }>();
		api.upload.mockReturnValueOnce(upload.promise);
		render(ImageStudio);
		await screen.findByRole('option', { name: 'high' });
		await fireEvent.change(screen.getByLabelText('입력 이미지'), { target: { files: [new File(['pixels'], 'source.png', { type: 'image/png' })] } });
		await screen.findByText('입력 이미지를 업로드하는 중…');
		expect(screen.getAllByRole('status').some((status) => status.textContent?.trim() === '입력 이미지를 업로드하는 중…')).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: /run-2/ }));
		await waitFor(() => expect(api.run).toHaveBeenCalledWith('run-2', { token: 'token', projectId: 'project-1' }));
		upload.resolve({ id: 'input-1', name: 'source.png', mime_type: 'image/png' });
		await screen.findByText('업로드 완료: source.png');
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'make it warmer' } });
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledWith('edits', expect.objectContaining({ input_asset_id: 'input-1', prompt: 'make it warmer' }), { token: 'token', projectId: 'project-1' }, expect.any(String), expect.any(AbortSignal)));
	});

	it('limits Gemini to one image and resets quantity when switching models', async () => {
		api.models.mockResolvedValue([ready, { ...ready, id: 2, model_name: 'gemini-image', display_name: 'Gemini Image', api_provider: 'gemini' }]);
		api.capabilities.mockImplementation(async (id: number) => ({ available_image_variants: ['1024x1024:high'], max_image_count: id === 2 ? 1 : 4 }));
		render(ImageStudio);
		await screen.findByRole('option', { name: 'Gemini Image' });
		await fireEvent.change(screen.getByRole('combobox', { name: '이미지 수' }), { target: { value: '3' } });
		await fireEvent.change(screen.getByRole('combobox', { name: '이미지 모델' }), { target: { value: '2' } });
		await waitFor(() => expect((screen.getByRole('combobox', { name: '이미지 수' }) as HTMLSelectElement).value).toBe('1'));
		expect(screen.queryByRole('option', { name: '3' })).toBeNull();
	});

	it('reuses an intent key after a lost response but changes it when the draft changes', async () => {
		api.submit.mockRejectedValueOnce(new Error('response lost')).mockRejectedValueOnce(new Error('response lost'));
		render(ImageStudio);
		await screen.findByRole('option', { name: 'high' });
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'sunrise' } });
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(1));
		await waitFor(() => expect((screen.getByRole('button', { name: '이미지 만들기' }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(2));
		expect(api.submit.mock.calls[1][3]).toBe(api.submit.mock.calls[0][3]);
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'sunset' } });
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(3));
		expect(api.submit.mock.calls[2][3]).not.toBe(api.submit.mock.calls[0][3]);
	});

	it('keeps a reference-generation input after a provider rejection and changes intent when the image is removed', async () => {
		api.submit.mockRejectedValueOnce(new ApiError(422, 'image input token price is unavailable'));
		render(ImageStudio);
		await screen.findByRole('option', { name: 'high' });
		await fireEvent.change(screen.getByLabelText('입력 이미지'), { target: { files: [new File(['pixels'], 'reference.png', { type: 'image/png' })] } });
		await screen.findByText('업로드 완료: source.png');
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: '이 캐릭터를 참고해서 새로운 우주 배경의 포스터를 그려줘.' } });
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		await screen.findByText('image input token price is unavailable');
		expect(api.submit).toHaveBeenCalledTimes(1);
		expect(api.submit.mock.calls[0][0]).toBe('edits');
		expect(api.submit.mock.calls[0][1].input_asset_id).toBe('input-1');
		expect(screen.getByRole('img', { name: '입력 이미지 미리보기' })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '첨부 이미지 제거' }));
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		await screen.findByRole('img', { name: '생성된 이미지' });
		expect(api.submit).toHaveBeenCalledTimes(2);
		expect(api.submit.mock.calls[1][0]).toBe('generations');
		expect(api.submit.mock.calls[1][1]).not.toHaveProperty('input_asset_id');
		expect(api.submit.mock.calls[1][3]).not.toBe(api.submit.mock.calls[0][3]);
	});

	it('blocks submission during upload and ignores its late success after input removal', async () => {
		const upload = Promise.withResolvers<{ id: string; name: string; mime_type: string }>();
		api.upload.mockReturnValueOnce(upload.promise);
		render(ImageStudio);
		await screen.findByRole('option', { name: 'high' });
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: '새로운 풍경을 그려줘.' } });
		await fireEvent.change(screen.getByLabelText('입력 이미지'), { target: { files: [new File(['pixels'], 'source.png', { type: 'image/png' })] } });
		await screen.findByText('입력 이미지를 업로드하는 중…');
		expect((screen.getByRole('button', { name: '이미지 만들기' }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.submit(screen.getByRole('form', { name: '이미지 요청' }));
		expect(api.submit).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '첨부 이미지 제거' }));
		expect(api.upload.mock.calls[0][2].aborted).toBe(true);
		upload.resolve({ id: 'obsolete-input', name: 'source.png', mime_type: 'image/png' });
		await upload.promise;
		expect(screen.queryByRole('img', { name: '입력 이미지 미리보기' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		await screen.findByRole('img', { name: '생성된 이미지' });
		expect(api.submit).toHaveBeenCalledTimes(1);
		expect(api.submit.mock.calls[0][0]).toBe('generations');
		expect(api.submit.mock.calls[0][1]).not.toHaveProperty('input_asset_id');
	});

	it('retains a failed upload and requires explicit removal before a text-only request', async () => {
		api.upload.mockRejectedValueOnce(new Error('upload unavailable'));
		render(ImageStudio);
		await screen.findByRole('option', { name: 'high' });
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: '첨부 이미지의 배경만 바꿔줘.' } });
		await fireEvent.change(screen.getByLabelText('입력 이미지'), { target: { files: [new File(['pixels'], 'source.png', { type: 'image/png' })] } });
		await screen.findByText(/입력 이미지 업로드 실패/);
		expect(screen.getByRole('img', { name: '입력 이미지 미리보기' })).toBeTruthy();
		expect((screen.getByRole('button', { name: '이미지 만들기' }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.submit(screen.getByRole('form', { name: '이미지 요청' }));
		expect(api.submit).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '첨부 이미지 제거' }));
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		await screen.findByRole('img', { name: '생성된 이미지' });
		expect(api.submit).toHaveBeenCalledTimes(1);
		expect(api.submit.mock.calls[0][0]).toBe('generations');
		expect(api.submit.mock.calls[0][1]).not.toHaveProperty('input_asset_id');
	});

	it('cancels an active run and reports the terminal cancellation', async () => {
		api.capabilities.mockResolvedValueOnce({ available_image_variants: ['1536x1024:high'], max_image_count: 1 });
		let canceled = false;
		api.run.mockImplementation(async () => ({ run_id: 'run-1', status: canceled ? 'canceled' : 'running', terminal: canceled, output_assets: [] }));
		api.cancel.mockImplementation(async () => { canceled = true; return {}; });
		render(ImageStudio);
		await screen.findByRole('option', { name: 'high' });
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'cloud' } });
		await waitFor(() => expect(screen.getByRole('button', { name: t('imageStudio.createImage') }).hasAttribute('disabled')).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: '이미지 만들기' }));
		expect(screen.queryByRole('img', { name: t('imageStudio.generatedImage') })).toBeNull();
		await fireEvent.click(await screen.findByRole('button', { name: '작업 취소' }));
		await screen.findByText('작업이 취소되었습니다.');
		expect(screen.queryByRole('img', { name: t('imageStudio.generatedImage') })).toBeNull();
	});
});

describe('image developing aspect ratio', () => {
	it('uses requested dimensions without pretending an automatic or unknown size is square', () => {
		expect(imageRequestAspectRatio('1536x1024')).toBe('1536 / 1024');
		expect(imageRequestAspectRatio('1024x1536')).toBe('1024 / 1536');
		expect(imageRequestAspectRatio('auto')).toBeNull();
		expect(imageRequestAspectRatio(null)).toBeNull();
		expect(imageRequestAspectRatio('0x1024')).toBeNull();
	});
});
