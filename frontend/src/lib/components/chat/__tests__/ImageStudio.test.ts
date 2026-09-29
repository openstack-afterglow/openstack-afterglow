import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import type * as ImageStudioModule from '$lib/api/imageStudio';
import ImageStudio from '../ImageStudio.svelte';

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
afterEach(() => vi.unstubAllGlobals());

describe('Image Studio', () => {
	it('blocks submission when image route or pricing is unavailable even if a model is listed', async () => {
		api.models.mockResolvedValue([{ ...ready, capabilities: { feature_gates: { image_output: { available: false, mode: 'none', pricing_available: false, reason_code: 'route_unavailable' } } } }]);
		render(ImageStudio);
		await screen.findByText(/route_unavailable/);
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'orange dusk' } });
		expect((screen.getByRole('button', { name: '이미지 생성 시작' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.submit).not.toHaveBeenCalled();
	});

	it('rejects an unpriced model variant and never submits a guessed default', async () => {
		api.capabilities.mockResolvedValue({ available_image_variants: [], max_image_count: 0 });
		render(ImageStudio);
		await screen.findByText('선택한 모델의 가격이 설정된 이미지 크기·품질을 사용할 수 없습니다.');
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'orange dusk' } });
		expect((screen.getByRole('button', { name: '이미지 생성 시작' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.submit).not.toHaveBeenCalled();
	});

	it('submits a ready generation, displays owned output and restores it from local history', async () => {
		const mounted = render(ImageStudio);
		await screen.findByRole('option', { name: 'Image Model' });
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'orange dusk' } });
		await fireEvent.click(screen.getByRole('button', { name: '이미지 생성 시작' }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledWith('generations', expect.objectContaining({ model_id: '1', prompt: 'orange dusk', size: '1024x1024', quality: 'high', n: 1 }), { token: 'token', projectId: 'project-1' }, expect.any(String), expect.any(AbortSignal)));
		await screen.findByRole('img', { name: '생성된 이미지' });
		expect(api.download).toHaveBeenCalledWith('asset-1', { token: 'token', projectId: 'project-1' }, expect.anything());
		mounted.unmount();
		render(ImageStudio);
		await screen.findByRole('img', { name: '생성된 이미지' });
		expect(api.run).toHaveBeenCalledWith('run-1', { token: 'token', projectId: 'project-1' });
	});

	it('uploads an edit input before submission and isolates project history', async () => {
		render(ImageStudio);
		await screen.findByRole('option', { name: 'Image Model' });
		await fireEvent.click(screen.getByRole('button', { name: '이미지 수정' }));
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'make it warmer' } });
		expect((screen.getByRole('button', { name: '이미지 수정 시작' }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.change(screen.getByLabelText('수정할 이미지'), { target: { files: [new File(['pixels'], 'source.png', { type: 'image/png' })] } });
		await screen.findByText('업로드 완료: source.png');
		await fireEvent.click(screen.getByRole('button', { name: '이미지 수정 시작' }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledWith('edits', expect.objectContaining({ model_id: '1', input_asset_id: 'input-1' }), { token: 'token', projectId: 'project-1' }, expect.any(String), expect.any(AbortSignal)));
		await screen.findByRole('img', { name: '생성된 이미지' });
		auth.set({ ...owner, projectId: 'project-2' });
		await waitFor(() => expect(screen.queryByRole('img', { name: '생성된 이미지' })).toBeNull());
		expect(screen.queryByRole('button', { name: /run-1/ })).toBeNull();
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
		await fireEvent.click(screen.getByRole('button', { name: '이미지 생성 시작' }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(1));
		await waitFor(() => expect((screen.getByRole('button', { name: '이미지 생성 시작' }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: '이미지 생성 시작' }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(2));
		expect(api.submit.mock.calls[1][3]).toBe(api.submit.mock.calls[0][3]);
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'sunset' } });
		await fireEvent.click(screen.getByRole('button', { name: '이미지 생성 시작' }));
		await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(3));
		expect(api.submit.mock.calls[2][3]).not.toBe(api.submit.mock.calls[0][3]);
	});

	it('cancels an active run and reports the terminal cancellation', async () => {
		api.run.mockResolvedValueOnce({ run_id: 'run-1', status: 'running', terminal: false, output_assets: [] })
			.mockResolvedValueOnce({ run_id: 'run-1', status: 'canceled', terminal: true, output_assets: [] });
		render(ImageStudio);
		await screen.findByRole('option', { name: 'Image Model' });
		await fireEvent.input(screen.getByRole('textbox', { name: /프롬프트/ }), { target: { value: 'cloud' } });
		await fireEvent.click(screen.getByRole('button', { name: '이미지 생성 시작' }));
		await fireEvent.click(await screen.findByRole('button', { name: '작업 취소' }));
		await waitFor(() => expect(api.cancel).toHaveBeenCalledWith('run-1', { token: 'token', projectId: 'project-1' }));
		await screen.findByText('작업이 취소되었습니다.');
	});
});
