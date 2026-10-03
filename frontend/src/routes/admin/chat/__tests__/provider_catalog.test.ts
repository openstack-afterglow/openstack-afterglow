import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
	class ApiError extends Error {
		constructor(message: string, public status: number) { super(message); }
	}
	return {
		get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(),
		confirm: vi.fn(), invalidate: vi.fn(), ApiError
	};
});
vi.mock('$lib/stores/auth', () => {
	const { readable } = require('svelte/store');
	return { auth: readable({ token: 'token', projectId: 'project' }) };
});
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: mocks.post, patch: mocks.patch, delete: mocks.delete },
	ApiError: mocks.ApiError
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/stores/chatModels', () => ({ invalidateChatModels: mocks.invalidate }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import ProviderPage from '../+page.svelte';
import ModelPage from '../models/+page.svelte';

const nim = {
	id: 7, name: 'NVIDIA NIM', provider_type: 'openai', api_provider: 'openai', sort_order: 20,
	api_base: 'https://nim.example/v1', auth_mode: 'api_key', has_api_key: true,
	has_credentials: true, is_active: true, margin_multiplier: 1, models_dev_provider_id: null
};
const other = { ...nim, id: 2, name: 'Other', api_provider: 'other', sort_order: 0 };
const empty = { ...nim, id: 9, name: 'Empty', api_provider: 'empty', sort_order: 20 };
const model = {
	id: 70, provider_id: 7, model_name: 'openai/nemotron', api_model_name: 'nemotron',
	api_provider: 'openai', display_name: 'Nemotron', sort_order: 10, is_active: true,
	is_title_model: true, model_kind: 'text', price_source: 'manual',
	input_price_per_million: '1.25', output_price_per_million: '5',
	effective_input_price_per_million: '1.25', effective_output_price_per_million: '5',
	effective_price_source: 'manual', capabilities: { vision: true },
	cache_read_price_per_million: '0.2', models_dev_model_id: null
};
const second = { ...model, id: 71, display_name: 'Second', model_name: 'openai/second', sort_order: 0, is_title_model: false };
const hidden = { ...model, id: 20, provider_id: 2, display_name: 'Hidden', model_name: 'openai/hidden', sort_order: 100, is_title_model: false };
let providers: typeof nim[];
let models: typeof model[];

function modelRow(id: number): HTMLElement {
	const checkbox = screen.getByRole('checkbox', { name: `${models.find((row) => row.id === id)!.display_name} 선택` });
	return checkbox.closest('[data-model-id]') as HTMLElement;
}
function providerRow(id: number): HTMLElement {
	return screen.getByText(providers.find((row) => row.id === id)!.name).closest('[data-provider-id]') as HTMLElement;
}
function rowOrder(container: HTMLElement): number[] {
	return Array.from(container.querySelectorAll('[data-model-id]'), (row) => Number(row.getAttribute('data-model-id')));
}
function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((done) => { resolve = done; });
	return { promise, resolve };
}

beforeEach(() => {
	vi.resetAllMocks();
	providers = [{ ...nim }, { ...empty }, { ...other }];
	models = [{ ...model }, { ...hidden }, { ...second }];
	mocks.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/chat/admin/providers') return providers.map((row) => ({ ...row }));
		if (path === '/api/v1/chat/admin/models') return models.map((row) => ({ ...row }));
		return [];
	});
	mocks.patch.mockImplementation(async (path: string, body: Record<string, unknown>) => {
		const id = Number(path.split('/').at(-1));
		if (path.includes('/providers/')) {
			providers = providers.map((row) => row.id === id ? { ...row, ...body } : row);
			models = models.map((row) => row.provider_id === id && 'api_provider' in body ? { ...row, api_provider: String(body.api_provider) } : row);
		} else {
			models = models.map((row) => row.id === id ? { ...row, ...body } : row);
		}
		return {};
	});
	mocks.delete.mockImplementation(async (path: string) => {
		models = models.filter((row) => row.id !== Number(path.split('/').at(-1)));
	});
	mocks.confirm.mockResolvedValue(true);
});

describe('provider catalog administration', () => {
	it('renames the public qualifier without changing the connection and preserves a rejected draft for retry', async () => {
		render(ProviderPage);
		await screen.findByText('NVIDIA NIM');
		await fireEvent.click(within(providerRow(7)).getByRole('button', { name: '표시 설정 수정' }));
		const dialog = screen.getByRole('dialog', { name: '프로바이더 표시 설정' });
		expect(within(dialog).getByText('openai')).toBeTruthy();
		await fireEvent.input(within(dialog).getByRole('textbox', { name: '표시 이름' }), { target: { value: 'NVIDIA' } });
		await fireEvent.input(within(dialog).getByRole('textbox', { name: 'API provider' }), { target: { value: 'nvidia' } });
		await fireEvent.input(within(dialog).getByRole('textbox', { name: '프로바이더 표시 순서' }), { target: { value: '0' } });
		mocks.patch.mockRejectedValueOnce(new mocks.ApiError('private upstream details', 409));
		await fireEvent.click(within(dialog).getByRole('button', { name: '저장' }));
		await within(dialog).findByRole('alert');
		expect((within(dialog).getByRole('textbox', { name: '표시 이름' }) as HTMLInputElement).value).toBe('NVIDIA');
		expect((within(dialog).getByRole('textbox', { name: 'API provider' }) as HTMLInputElement).value).toBe('nvidia');
		expect((within(dialog).getByRole('textbox', { name: '프로바이더 표시 순서' }) as HTMLInputElement).value).toBe('0');
		expect(screen.queryByText('private upstream details')).toBeNull();
		expect(within(providerRow(7)).getByText('NVIDIA NIM')).toBeTruthy();
		await fireEvent.click(within(dialog).getByRole('button', { name: '저장' }));
		await screen.findByText('NVIDIA');
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
		expect(within(providerRow(7)).getByText('연결: openai')).toBeTruthy();
		expect(within(providerRow(7)).getByText('nvidia')).toBeTruthy();
		await fireEvent.click(within(providerRow(7)).getByRole('button', { name: '표시 설정 수정' }));
		expect((screen.getByRole('textbox', { name: '표시 이름' }) as HTMLInputElement).value).toBe('NVIDIA');
	});

	it('keeps independent creation fields and credentials after a failed create, then publishes server data on retry', async () => {
		render(ProviderPage);
		await screen.findByText('NVIDIA NIM');
		await fireEvent.input(screen.getByRole('textbox', { name: '이름' }), { target: { value: 'New NVIDIA' } });
		await fireEvent.input(screen.getByRole('textbox', { name: 'API provider' }), { target: { value: 'nvidia' } });
		await fireEvent.input(screen.getByRole('textbox', { name: '프로바이더 표시 순서' }), { target: { value: '3' } });
		await fireEvent.input(screen.getByLabelText('API Base'), { target: { value: 'https://new.example/v1' } });
		await fireEvent.input(screen.getByLabelText('API 키'), { target: { value: 'draft-secret' } });
		mocks.post.mockRejectedValueOnce(new mocks.ApiError('draft-secret', 503));
		await fireEvent.click(screen.getByRole('button', { name: '+ 프로바이더 추가' }));
		await screen.findByRole('alert');
		expect((screen.getByRole('textbox', { name: 'API provider' }) as HTMLInputElement).value).toBe('nvidia');
		expect((screen.getByRole('textbox', { name: '프로바이더 표시 순서' }) as HTMLInputElement).value).toBe('3');
		expect((screen.getByLabelText('API Base') as HTMLInputElement).value).toBe('https://new.example/v1');
		expect((screen.getByLabelText('API 키') as HTMLInputElement).value).toBe('draft-secret');
		mocks.post.mockImplementationOnce(async (_path: string, body: Record<string, unknown>) => {
			const created = { ...nim, ...body, id: 12 };
			providers.push(created);
			return created;
		});
		await fireEvent.click(screen.getByRole('button', { name: '+ 프로바이더 추가' }));
		await screen.findByText('New NVIDIA');
		expect(within(providerRow(12)).getByText('연결: openai')).toBeTruthy();
		expect(within(providerRow(12)).getByText('nvidia')).toBeTruthy();
		expect((screen.getByLabelText('API 키') as HTMLInputElement).value).toBe('');
	});

	it('refuses invalid provider qualifiers, blank names and out-of-range or fractional order before mutation', async () => {
		render(ProviderPage);
		await screen.findByText('NVIDIA NIM');
		await fireEvent.click(within(providerRow(7)).getByRole('button', { name: '표시 설정 수정' }));
		const dialog = screen.getByRole('dialog');
		for (const value of ['', 'NVIDIA', '1nvidia', 'bad/value', 'a'.repeat(41)]) {
			await fireEvent.input(within(dialog).getByRole('textbox', { name: 'API provider' }), { target: { value } });
			await fireEvent.click(within(dialog).getByRole('button', { name: '저장' }));
			expect(within(dialog).getByRole('textbox', { name: 'API provider' }).getAttribute('aria-invalid')).toBe('true');
		}
		await fireEvent.input(within(dialog).getByRole('textbox', { name: 'API provider' }), { target: { value: 'nvidia' } });
		for (const value of ['', '-1', '1.5', '2147483648', 'Infinity', '1e2']) {
			await fireEvent.input(within(dialog).getByRole('textbox', { name: '프로바이더 표시 순서' }), { target: { value } });
			await fireEvent.click(within(dialog).getByRole('button', { name: '저장' }));
			expect(within(dialog).getByRole('textbox', { name: '프로바이더 표시 순서' }).getAttribute('aria-invalid')).toBe('true');
		}
		await fireEvent.input(within(dialog).getByRole('textbox', { name: '프로바이더 표시 순서' }), { target: { value: '2147483647' } });
		await fireEvent.input(within(dialog).getByRole('textbox', { name: '표시 이름' }), { target: { value: '  ' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: '저장' }));
		expect(within(dialog).getByRole('textbox', { name: '표시 이름' }).getAttribute('aria-invalid')).toBe('true');
		expect(mocks.patch).not.toHaveBeenCalled();
	});

	it('uses rank then ID ordering for provider rows, all provider controls and registered models', async () => {
		providers = [{ ...nim, sort_order: 0 }, { ...empty, sort_order: 0 }, { ...other, sort_order: 5 }];
		models = [{ ...model, sort_order: 0 }, { ...second, sort_order: 0 }, { ...hidden }];
		const view = render(ProviderPage);
		await screen.findByText('NVIDIA NIM');
		expect(Array.from(view.container.querySelectorAll('[data-provider-id]'), (row) => Number(row.getAttribute('data-provider-id')))).toEqual([7, 9, 2]);
		view.unmount();
		const modelView = render(ModelPage);
		await screen.findByRole('checkbox', { name: 'Nemotron 선택' });
		expect(rowOrder(modelView.container)).toEqual([70, 71, 20]);
		for (const label of ['조회 프로바이더', '수동 등록 프로바이더', '등록 모델 프로바이더 필터']) {
			expect(within(screen.getByLabelText(label)).getAllByRole('option').slice(1).map((option) => option.textContent)).toEqual(['NVIDIA NIM', 'Empty', 'Other']);
		}
	});

	it('clears selection on registered filter changes and bulk deletes only visible models independently of creation selection', async () => {
		const view = render(ModelPage);
		await screen.findByRole('checkbox', { name: 'Nemotron 선택' });
		await fireEvent.change(screen.getByLabelText('조회 프로바이더'), { target: { value: '2' } });
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Hidden 선택' }));
		await fireEvent.change(screen.getByLabelText('등록 모델 프로바이더 필터'), { target: { value: '7' } });
		expect(screen.queryByRole('button', { name: /선택 삭제/ })).toBeNull();
		expect(screen.queryByRole('checkbox', { name: 'Hidden 선택' })).toBeNull();
		expect((screen.getByLabelText('조회 프로바이더') as HTMLSelectElement).value).toBe('2');
		expect((screen.getByLabelText('수동 등록 프로바이더') as HTMLSelectElement).value).toBe('2');
		expect(rowOrder(view.container)).toEqual([71, 70]);
		for (const action of ['가격 수정', '기능 수정', '순서 수정', '비활성화', '제목요약 해제', '삭제']) {
			expect(within(modelRow(70)).getByRole('button', { name: action })).toBeTruthy();
		}
		await fireEvent.click(screen.getByRole('checkbox', { name: '전체 선택' }));
		await fireEvent.click(screen.getByRole('button', { name: '선택 삭제 (2)' }));
		await screen.findByText('선택한 프로바이더에 등록된 모델이 없습니다.');
		expect(models.map((row) => row.id)).toEqual([20]);
		await fireEvent.change(screen.getByLabelText('등록 모델 프로바이더 필터'), { target: { value: '' } });
		expect((await screen.findByRole('checkbox', { name: 'Hidden 선택' }) as HTMLInputElement).checked).toBe(false);
	});

	it('does not delete hidden rows when the filter changes while confirmation is open', async () => {
		const confirmation = deferred<boolean>();
		mocks.confirm.mockReturnValueOnce(confirmation.promise);
		render(ModelPage);
		await screen.findByRole('checkbox', { name: 'Nemotron 선택' });
		await fireEvent.click(screen.getByRole('checkbox', { name: '전체 선택' }));
		await fireEvent.click(screen.getByRole('button', { name: '선택 삭제 (3)' }));
		await fireEvent.change(screen.getByLabelText('등록 모델 프로바이더 필터'), { target: { value: '2' } });
		confirmation.resolve(true);
		await confirmation.promise;
		await waitFor(() => expect(screen.queryByRole('button', { name: /선택 삭제/ })).toBeNull());
		expect(mocks.delete).not.toHaveBeenCalled();
		expect(models.map((row) => row.id)).toEqual([70, 20, 71]);
	});

	it('drops stale selected IDs on reload so a later reappearing row is not selected', async () => {
		render(ModelPage);
		await screen.findByRole('checkbox', { name: 'Nemotron 선택' });
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Nemotron 선택' }));
		models = models.filter((row) => row.id !== 70);
		await fireEvent.click(within(modelRow(71)).getByRole('button', { name: '비활성화' }));
		await screen.findByRole('button', { name: '활성화' });
		expect(screen.queryByRole('checkbox', { name: 'Nemotron 선택' })).toBeNull();
		expect(screen.queryByRole('button', { name: /선택 삭제/ })).toBeNull();
		models.push({ ...model });
		await fireEvent.click(within(modelRow(71)).getByRole('button', { name: '활성화' }));
		expect((await screen.findByRole('checkbox', { name: 'Nemotron 선택' }) as HTMLInputElement).checked).toBe(false);
	});

	it('edits model rank with retryable drafts without altering pricing, capabilities, title or activation', async () => {
		const view = render(ModelPage);
		await screen.findByRole('checkbox', { name: 'Nemotron 선택' });
		expect(rowOrder(view.container)).toEqual([20, 71, 70]);
		await fireEvent.click(within(modelRow(70)).getByRole('button', { name: '순서 수정' }));
		const dialog = screen.getByRole('dialog', { name: '모델 표시 순서' });
		const input = within(dialog).getByRole('textbox', { name: '모델 표시 순서' });
		for (const value of ['', '-1', '0.5', '2147483648']) {
			await fireEvent.input(input, { target: { value } });
			await fireEvent.click(within(dialog).getByRole('button', { name: '저장' }));
			expect(input.getAttribute('aria-invalid')).toBe('true');
		}
		expect(mocks.patch).not.toHaveBeenCalled();
		await fireEvent.input(input, { target: { value: '0' } });
		mocks.patch.mockRejectedValueOnce(new mocks.ApiError('unsafe upstream details', 409));
		await fireEvent.click(within(dialog).getByRole('button', { name: '저장' }));
		await within(dialog).findByRole('alert');
		expect((input as HTMLInputElement).value).toBe('0');
		expect(rowOrder(view.container)).toEqual([20, 71, 70]);
		await fireEvent.click(within(dialog).getByRole('button', { name: '저장' }));
		await waitFor(() => expect(rowOrder(view.container)).toEqual([20, 70, 71]));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(within(modelRow(70)).getByText(/입력 1.25 · 출력 5 USD/)).toBeTruthy();
		expect(within(modelRow(70)).getByRole('button', { name: '제목요약 해제' })).toBeTruthy();
		expect(within(modelRow(70)).getByRole('button', { name: '비활성화' })).toBeTruthy();
	});

	it('does not overwrite server-side price or default changes made while the order editor is open', async () => {
		render(ModelPage);
		await screen.findByRole('checkbox', { name: 'Nemotron 선택' });
		await fireEvent.click(within(modelRow(70)).getByRole('button', { name: '순서 수정' }));
		const dialog = screen.getByRole('dialog', { name: '모델 표시 순서' });
		await fireEvent.input(within(dialog).getByRole('textbox', { name: '모델 표시 순서' }), { target: { value: '2147483647' } });
		const concurrent = {
			...model, input_price_per_million: '2', effective_input_price_per_million: '2',
			cache_read_price_per_million: '0.4', capabilities: { vision: false },
			is_active: false, is_title_model: false
		};
		models = models.map((row) => row.id === 70 ? concurrent : row);
		await fireEvent.click(within(dialog).getByRole('button', { name: '저장' }));
		await screen.findByText(/입력 2 · 출력 5 USD/);
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(within(modelRow(70)).getByText(/입력 2 · 출력 5 USD/)).toBeTruthy();
		expect(within(modelRow(70)).getByRole('button', { name: '제목요약 지정' })).toBeTruthy();
		expect(within(modelRow(70)).getByRole('button', { name: '활성화' })).toBeTruthy();
	});
});
