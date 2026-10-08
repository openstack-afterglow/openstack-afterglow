import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';

const mocks = vi.hoisted(() => {
	const { writable } = require('svelte/store');
	class ApiError extends Error {
		constructor(message: string, public status: number) { super(message); }
	}
	return {
		get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(),
		auth: writable({ token: 'token', projectId: 'project' }),
		authReady: writable(true), projectSwitching: writable(false),
		confirm: vi.fn(), invalidate: vi.fn(), ApiError
	};
});
vi.mock('$lib/stores/auth', () => ({ auth: mocks.auth, authReady: mocks.authReady, projectSwitching: mocks.projectSwitching }));
// Personal extension permissions are unrelated to these admin flows; do not consume API fixtures.
vi.mock('$lib/stores/servicePermissions', () => ({
	serviceCapabilities: writable<(leaf: string) => boolean>(() => false),
	projectPermissions: writable({ permissions: null, loading: false, error: '' })
}));
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
	return Promise.withResolvers<T>();
}

async function dragEvent(target: HTMLElement, type: string, properties: Record<string, unknown> = {}) {
	const event = new Event(type, { bubbles: true, cancelable: true });
	Object.assign(event, properties);
	await fireEvent(target, event);
	return event;
}
async function startDrag(target: HTMLElement) {
	await fireEvent.mouseDown(target, { button: 0 });
	return dragEvent(target, 'dragstart', { dataTransfer: { setData: vi.fn(), effectAllowed: 'none' } });
}
async function dragModel(source: HTMLElement, target: HTMLElement, edge: 'before' | 'after') {
	await startDrag(source);
	const clientY = edge === 'before' ? -1 : 1;
	await dragEvent(target, 'dragover', { clientY, dataTransfer: {} });
	await dragEvent(target, 'drop', { clientY });
	await dragEvent(source, 'dragend');
}

beforeEach(() => {
	vi.resetAllMocks();
	mocks.auth.set({ token: 'token', projectId: 'project' });
	mocks.authReady.set(true); mocks.projectSwitching.set(false);
	providers = [{ ...nim }, { ...empty }, { ...other }];
	models = [{ ...model }, { ...hidden }, { ...second }];
	mocks.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/chat/admin/providers') return providers.map((row) => ({ ...row }));
		if (path === '/api/v1/chat/admin/models') return models.map((row) => ({ ...row }));
		return [];
	});
	mocks.post.mockImplementation(async (path: string, body: { provider_id: number; model_ids: number[] }) => {
		if (path === '/api/v1/chat/admin/models/reorder') {
			const ranks = new Map(body.model_ids.map((id, index) => [id, index]));
			models = models.map((row) => row.provider_id === body.provider_id ? { ...row, sort_order: ranks.get(row.id)! } : row);
		}
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
		for (const action of ['가격 수정', '기능 수정', 'Nemotron 위로 이동', 'Nemotron 아래로 이동', '비활성화', '제목요약 해제', '삭제']) {
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

	it('drags a whole card before or after another card and retains its non-order configuration after reload', async () => {
		const view = render(ModelPage);
		await screen.findByRole('checkbox', { name: 'Nemotron 선택' });
		expect(rowOrder(view.container)).toEqual([20, 71, 70]);
		await dragModel(modelRow(70), modelRow(71), 'before');
		await waitFor(() => expect(rowOrder(view.container)).toEqual([20, 70, 71]));
		await waitFor(() => expect(modelRow(70).getAttribute('draggable')).toBe('true'));
		expect(within(modelRow(70)).getByText(/입력 1.25 · 출력 5 USD/)).toBeTruthy();
		expect(within(modelRow(70)).getByRole('button', { name: '제목요약 해제' })).toBeTruthy();
		expect(within(modelRow(70)).getByRole('button', { name: '비활성화' })).toBeTruthy();
		await dragModel(modelRow(70), modelRow(71), 'after');
		await waitFor(() => expect(rowOrder(view.container)).toEqual([20, 71, 70]));
		await waitFor(() => expect(modelRow(70).getAttribute('draggable')).toBe('true'));
		view.unmount();
		const reloaded = render(ModelPage);
		await screen.findByRole('checkbox', { name: 'Nemotron 선택' });
		expect(rowOrder(reloaded.container)).toEqual([20, 71, 70]);
	});

	it('permutes kind-filtered visible slots without moving hidden models or another provider', async () => {
		models.push({ ...model, id: 72, display_name: 'Image', model_name: 'openai/image', model_kind: 'image', sort_order: 5 });
		const view = render(ModelPage);
		await screen.findByRole('checkbox', { name: 'Nemotron 선택' });
		await fireEvent.change(screen.getByLabelText('등록 모델 종류 필터'), { target: { value: 'text' } });
		await dragModel(modelRow(70), modelRow(71), 'before');
		await waitFor(() => expect(modelRow(70).getAttribute('draggable')).toBe('true'));
		expect(rowOrder(view.container)).toEqual([20, 70, 71]);
		await fireEvent.change(screen.getByLabelText('등록 모델 종류 필터'), { target: { value: '' } });
		expect(rowOrder(view.container)).toEqual([20, 70, 72, 71]);
		expect(models.find((row) => row.id === 20)?.sort_order).toBe(100);
	});

	it('restores server order after a conflict, keeps concurrent price changes and permits a keyboard/touch retry', async () => {
		const view = render(ModelPage);
		await screen.findByRole('checkbox', { name: 'Nemotron 선택' });
		mocks.post.mockImplementationOnce(async () => {
			models = models.map((row) => row.id === 70 ? { ...row, effective_input_price_per_million: '2', is_active: false, is_title_model: false } : row);
			throw new mocks.ApiError('unsafe upstream details', 409);
		});
		await dragModel(modelRow(70), modelRow(71), 'before');
		await screen.findByRole('alert');
		await screen.findByText(/입력 2 · 출력 5 USD/);
		expect(rowOrder(view.container)).toEqual([20, 71, 70]);
		expect(screen.queryByText('unsafe upstream details')).toBeNull();
		await fireEvent.click(within(modelRow(70)).getByRole('button', { name: 'Nemotron 위로 이동' }));
		await waitFor(() => expect(rowOrder(view.container)).toEqual([20, 70, 71]));
		await waitFor(() => expect(document.activeElement).toBe(within(modelRow(70)).getByRole('button', { name: 'Nemotron 아래로 이동' })));
		expect(screen.queryByRole('alert')).toBeNull();
		expect(within(modelRow(70)).getByRole('button', { name: '활성화' })).toBeTruthy();
		expect(within(modelRow(70)).getByRole('button', { name: '제목요약 지정' })).toBeTruthy();
	});

	it('ignores cross-provider drops, drags starting on a control, canceled drags and filter changes mid-drag', async () => {
		const view = render(ModelPage);
		await screen.findByRole('checkbox', { name: 'Nemotron 선택' });
		await dragModel(modelRow(70), modelRow(20), 'before');
		const control = within(modelRow(70)).getByRole('button', { name: '가격 수정' });
		await fireEvent.mouseDown(control, { button: 0 });
		expect((await dragEvent(modelRow(70), 'dragstart', { dataTransfer: { setData: vi.fn() } })).defaultPrevented).toBe(true);
		await startDrag(modelRow(70));
		await dragEvent(modelRow(70), 'dragend');
		await dragEvent(modelRow(71), 'drop', { clientY: -1 });
		await startDrag(modelRow(70));
		await fireEvent.change(screen.getByLabelText('등록 모델 종류 필터'), { target: { value: 'text' } });
		await dragEvent(modelRow(71), 'drop', { clientY: -1 });
		expect(rowOrder(view.container)).toEqual([20, 71, 70]);
		expect(mocks.post).not.toHaveBeenCalled();
		await fireEvent.click(control);
		expect((within(screen.getByRole('dialog')).getByLabelText('입력') as HTMLInputElement).value).toBe('1.25');
	});

	it('blocks overlapping reorders and discards a late failure after the auth scope changes', async () => {
		const pending = Promise.withResolvers<void>();
		mocks.post.mockReturnValueOnce(pending.promise);
		const view = render(ModelPage);
		await screen.findByRole('checkbox', { name: 'Nemotron 선택' });
		await dragModel(modelRow(70), modelRow(71), 'before');
		expect((within(modelRow(70)).getByRole('button', { name: 'Nemotron 아래로 이동' }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByLabelText('등록 모델 프로바이더 필터') as HTMLSelectElement).disabled).toBe(true);
		models = [{ ...model, id: 90, display_name: 'Fresh A', sort_order: 0 }, { ...model, id: 91, display_name: 'Fresh B', sort_order: 1 }];
		mocks.auth.set({ token: 'fresh-token', projectId: 'fresh-project' });
		await screen.findByRole('checkbox', { name: 'Fresh A 선택' });
		pending.reject(new mocks.ApiError('old-scope-error', 503));
		await waitFor(() => expect(rowOrder(view.container)).toEqual([90, 91]));
		expect(screen.queryByRole('alert')).toBeNull();
		expect((within(modelRow(90)).getByRole('button', { name: 'Fresh A 아래로 이동' }) as HTMLButtonElement).disabled).toBe(false);
	});
});
