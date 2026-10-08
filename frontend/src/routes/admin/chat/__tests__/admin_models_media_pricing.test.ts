import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';

const mocks = vi.hoisted(() => {
	class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
	return {
		get: vi.fn(), post: vi.fn(), patch: vi.fn(), success: vi.fn(), error: vi.fn(),
		scope: { token: 'token', projectId: 'project', isSystemAdmin: true },
		listeners: new Set<(scope: { token: string; projectId: string; isSystemAdmin: boolean }) => void>(), ApiError
	};
});
vi.mock('$lib/stores/auth', () => ({
	auth: { subscribe(run: (scope: typeof mocks.scope) => void) { mocks.listeners.add(run); run(mocks.scope); return () => mocks.listeners.delete(run); } },
	authReady: writable(true), projectSwitching: writable(false)
}));
// Personal extension permissions are unrelated to these admin flows; do not consume API fixtures.
vi.mock('$lib/stores/servicePermissions', () => ({
	serviceCapabilities: writable<(leaf: string) => boolean>(() => false),
	projectPermissions: writable({ permissions: null, loading: false, error: '' })
}));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, post: mocks.post, patch: mocks.patch, put: vi.fn(), delete: vi.fn() }, ApiError: mocks.ApiError }));
vi.mock('$lib/stores/chatModels', () => ({ invalidateChatModels: vi.fn() }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: mocks.success, error: mocks.error } }));
import { authReady, projectSwitching } from '$lib/stores/auth';
import ModelPage from '../models/+page.svelte';

const provider = { id: 1, name: 'OpenAI', provider_type: 'openai', api_base: null, auth_mode: 'api_key', has_api_key: true, models_dev_provider_id: 'openai', is_active: true, margin_multiplier: 1 };
function model(kind = 'image', pricing: Record<string, unknown> = {}) {
	return { id: 1, provider_id: 1, model_name: 'opaque-model', api_model_name: 'opaque-model', display_name: 'Media model', model_kind: kind, is_active: false,
		input_price_per_million: '2.0000000000', output_price_per_million: '8.0000000000', effective_input_price_per_million: '2', effective_output_price_per_million: '8',
		cache_read_price_per_million: '0.3000000000', cache_write_price_per_million: '3.75', cache_write_1h_price_per_million: '6',
		price_source: 'models.dev', models_dev_model_id: 'catalog-model', media_pricing: pricing };
}
let rows: Record<string, unknown>[];
let candidates: Record<string, unknown>[];
async function openEditor() {
	await fireEvent.click(await screen.findByText('가격 수정'));
	return screen.getByRole('dialog', { name: '모델 가격 수정' });
}
beforeEach(() => {
	vi.clearAllMocks();
	mocks.scope = { token: 'token', projectId: 'project', isSystemAdmin: true };
	authReady.set(true); projectSwitching.set(false);
	rows = []; candidates = [];
	mocks.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/chat/admin/providers') return [provider];
		if (path === '/api/v1/chat/admin/models') return rows;
		if (path.endsWith('/available-models')) return { provider_id: 1, source: 'api', live_status: 'success', complete: true, fetched_at: '', error: null, candidates, models: candidates.map((candidate) => candidate.id) };
		return [];
	});
	mocks.post.mockResolvedValue({});
	mocks.patch.mockImplementation(async (_path: string, body: Record<string, unknown>) => { rows = rows.map((row) => ({ ...row, ...body })); return {}; });
});
afterEach(cleanup);

describe('admin multimodal pricing consumer', () => {
	it('filters registered image models independently and clears hidden selections', async () => {
		rows = [model(), { ...model('text'), id: 2, display_name: 'Text model' }]; render(ModelPage);
		await fireEvent.click(await screen.findByRole('checkbox', { name: 'Media model 선택' }));
		expect(screen.getByRole('button', { name: '선택 삭제 (1)' })).toBeTruthy();
		await fireEvent.change(screen.getByLabelText('등록 모델 종류 필터'), { target: { value: 'text' } });
		expect(screen.queryByRole('checkbox', { name: 'Media model 선택' })).toBeNull();
		expect(screen.getByRole('checkbox', { name: 'Text model 선택' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: '선택 삭제 (1)' })).toBeNull();
		await fireEvent.change(screen.getByLabelText('등록 모델 종류 필터'), { target: { value: 'image' } });
		expect((screen.getByRole('checkbox', { name: 'Media model 선택' }) as HTMLInputElement).checked).toBe(false);
		expect(screen.queryByRole('checkbox', { name: 'Text model 선택' })).toBeNull();
	});
	it('requires positive token reservation and saves text/cache and media token rates independently', async () => {
		rows = [model('image', { image_per_unit: '0.04' })]; render(ModelPage);
		const modal = await openEditor();
		await fireEvent.change(within(modal).getByLabelText('이미지 과금 기준'), { target: { value: 'tokens' } });
		await fireEvent.input(within(modal).getByLabelText('요청 전체 예약 상한'), { target: { value: '0' } });
		await fireEvent.input(within(modal).getByLabelText('캐시 읽기'), { target: { value: '0' } });
		await fireEvent.input(within(modal).getByLabelText('이미지 출력'), { target: { value: '40' } });
		await fireEvent.click(within(modal).getByRole('button', { name: '저장' }));
		expect(mocks.patch).not.toHaveBeenCalled();
		await fireEvent.input(within(modal).getByLabelText('요청 전체 예약 상한'), { target: { value: '1.5000' } });
		await fireEvent.click(within(modal).getByRole('button', { name: '저장' }));
		await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith('/api/v1/chat/admin/models/1', {
			cache_read_price_per_million: '0', media_pricing: { image_per_unit: '0.04', billing_basis: 'tokens', reservation_usd: '1.5000', token_rates: { image: { output_per_million: '40' } } }
		}, 'token', 'project'));
	});
	it.each([
		{ kind: 'text', label: '입력', key: 'input_price_per_million', value: '5' },
		{ kind: undefined, label: '입력', key: 'input_price_per_million', value: '5' },
		{ kind: 'image', label: '입력', key: 'input_price_per_million', value: '5' },
		{ kind: 'tts', label: '입력', key: 'input_price_per_million', value: '2' },
		{ kind: 'stt', label: '출력', key: 'output_price_per_million', value: '4' },
		{ kind: 'realtime', label: '입력', key: 'input_price_per_million', value: '0' }
	])('saves $kind applicable text $label without inventing the unused direction', async ({ kind, label, key, value }) => {
		rows = [{ ...model(), model_kind: kind, input_price_per_million: null, output_price_per_million: null, effective_input_price_per_million: null, effective_output_price_per_million: null }];
		render(ModelPage);
		const modal = await openEditor();
		await fireEvent.input(within(modal).getByLabelText(label), { target: { value: ` ${value} ` } });
		await fireEvent.click(within(modal).getByRole('button', { name: '저장' }));
		await waitFor(() => expect(screen.queryByRole('dialog', { name: '모델 가격 수정' })).toBeNull());
		const reopened = await openEditor();
		expect((within(reopened).getByLabelText(label) as HTMLInputElement).value).toBe(value);
		expect((within(reopened).getByLabelText(label === '입력' ? '출력' : '입력') as HTMLInputElement).value).toBe('');
		expect(mocks.patch).toHaveBeenCalledWith('/api/v1/chat/admin/models/1', { [key]: value }, 'token', 'project');
		expect(mocks.error).not.toHaveBeenCalled();
	});
	it.each(['입력', '출력'])('stores a discovered text candidate inactive with only its %s price', async (direction) => {
		candidates = [{ id: 'partial-candidate', display_name: 'Partial candidate', purpose: 'chat', model_kind: 'text' }];
		mocks.post.mockImplementation(async (_path: string, body: Record<string, unknown>) => {
			rows = [{ ...model('text'), input_price_per_million: null, output_price_per_million: null, ...body }];
			return rows[0];
		});
		render(ModelPage);
		await screen.findAllByRole('option', { name: 'OpenAI' });
		await fireEvent.click(screen.getByRole('button', { name: '모델 불러오기' }));
		await fireEvent.click(await screen.findByRole('checkbox', { name: 'partial-candidate' }));
		await fireEvent.click(screen.getByRole('button', { name: '선택 모델 검토' }));
		await fireEvent.input(screen.getByLabelText(`${direction} 단가 · partial-candidate`), { target: { value: '1.25' } });
		expect((screen.getByRole('button', { name: '가격 확인 후 등록·활성화' }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '비활성으로 저장' }));
		await waitFor(() => expect(screen.queryByTestId('model-registration-review')).toBeNull());
		await screen.findByText('비활성 · 저장됨');
		const modal = await openEditor();
		expect((within(modal).getByLabelText(direction) as HTMLInputElement).value).toBe('1.25');
		expect((within(modal).getByLabelText(direction === '입력' ? '출력' : '입력') as HTMLInputElement).value).toBe('');
		expect(mocks.error).not.toHaveBeenCalled();
	});

	it('filters image-output discovery, registers its explicit kind inactive, and leaves text candidates alone', async () => {
		candidates = [{ id: 'opaque-image', purpose: 'non_chat', model_kind: 'image' }, { id: 'opaque-text', purpose: 'chat', model_kind: 'text' }];
		render(ModelPage);
		await screen.findAllByRole('option', { name: 'OpenAI' });
		await fireEvent.click(screen.getByRole('button', { name: '모델 불러오기' }));
		await screen.findByRole('checkbox', { name: 'opaque-image' });
		await fireEvent.change(screen.getByLabelText('후보 종류 필터'), { target: { value: 'image' } });
		expect(screen.queryByRole('checkbox', { name: 'opaque-text' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '전체 선택' }));
		await fireEvent.click(screen.getByRole('button', { name: '선택 모델 검토' }));
		expect((screen.getByLabelText('모델 종류 · opaque-image') as HTMLSelectElement).value).toBe('image');
		await fireEvent.click(screen.getByRole('button', { name: '비활성으로 저장' }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/admin/models', { provider_id: 1, model_name: 'opaque-image', model_kind: 'image', is_active: false }, 'token', 'project'));
	});
	it('requires an explicit manual kind for unknown non-chat candidates', async () => {
		candidates = [{ id: 'unclassified', purpose: 'non_chat', model_kind: null }];
		render(ModelPage);
		await screen.findAllByRole('option', { name: 'OpenAI' });
		await fireEvent.click(screen.getByRole('button', { name: '모델 불러오기' }));
		await fireEvent.click(await screen.findByRole('checkbox', { name: 'unclassified' }));
		await fireEvent.click(screen.getByRole('button', { name: '선택 모델 검토' }));
		expect((screen.getByRole('button', { name: '비활성으로 저장' }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.change(screen.getByLabelText('모델 종류 · unclassified'), { target: { value: 'tts' } });
		await fireEvent.click(screen.getByRole('button', { name: '비활성으로 저장' }));
		await waitFor(() => expect(mocks.post.mock.calls[0][1]).toEqual({ provider_id: 1, model_name: 'unclassified', model_kind: 'tts', is_active: false }));
	});
	it('edits multimodal cached rates without changing text/catalog prices or unknown JSON, and reopens saved values', async () => {
		const pricing = { image_per_unit: '0.04', image_variants: { '1024x1024:high': '0.08' }, vendor_extension: { tier: 'kept' }, token_rates: {
			image: { input_per_million: '5', cache_read_per_million: '1.2500000000', output_per_million: '40', future_rate: '7' },
			audio: { input_per_million: '9', cache_read_per_million: '0', output_per_million: '18' }
		} };
		rows = [model('image', pricing)];
		render(ModelPage);
		const modal = await openEditor();
		expect((within(modal).getByLabelText('캐시 읽기') as HTMLInputElement).value).toBe('0.3');
		await fireEvent.input(within(modal).getByLabelText('이미지 캐시 입력'), { target: { value: '0' } });
		await fireEvent.input(within(modal).getByLabelText('오디오 캐시 입력'), { target: { value: '' } });
		await fireEvent.click(within(modal).getByRole('button', { name: '저장' }));
		const expected = { ...pricing, token_rates: { image: { ...pricing.token_rates.image, cache_read_per_million: '0' }, audio: { input_per_million: '9', output_per_million: '18' } } };
		await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith('/api/v1/chat/admin/models/1', { media_pricing: expected }, 'token', 'project'));
		await waitFor(() => expect(screen.queryByRole('dialog', { name: '모델 가격 수정' })).toBeNull());
		const reopened = await openEditor();
		expect((within(reopened).getByLabelText('이미지 캐시 입력') as HTMLInputElement).value).toBe('0');
		expect((within(reopened).getByLabelText('오디오 캐시 입력') as HTMLInputElement).value).toBe('');
		expect((within(reopened).getByLabelText('입력') as HTMLInputElement).value).toBe('2.0000000000');
		await fireEvent.click(within(reopened).getByRole('button', { name: '저장' }));
		expect(mocks.patch).toHaveBeenCalledTimes(1);
	});
	it('does not prune untouched empty supported JSON while saving a different price', async () => {
		rows = [model('image', { image_per_unit: '0.04', token_rates: { image: {}, audio: {} }, image_variants: {} })]; render(ModelPage);
		const modal = await openEditor();
		await fireEvent.input(within(modal).getByLabelText('이미지 기본 단가'), { target: { value: '0' } });
		await fireEvent.click(within(modal).getByRole('button', { name: '저장' }));
		await waitFor(() => expect(mocks.patch.mock.calls[0][1]).toEqual({ media_pricing: { image_per_unit: '0', token_rates: { image: {}, audio: {} }, image_variants: {} } }));
	});
	it.each(['tts', 'stt', 'realtime'])('stores %s hourly audio pricing verbatim without deleting legacy rates', async (kind) => {
		const legacy = kind === 'tts' ? { audio_per_second: '0.001' } : kind === 'stt' ? { audio_per_minute: '0.06' } : { realtime_input_per_minute: '0.06', realtime_output_per_minute: '0.12' };
		rows = [model(kind, legacy)]; render(ModelPage);
		const modal = await openEditor(), direction = kind === 'tts' ? '출력' : '입력';
		await fireEvent.change(within(modal).getByLabelText(`${direction} 시간 단위`), { target: { value: 'hour' } });
		await fireEvent.input(within(modal).getByLabelText(`${direction} 시간 단가`), { target: { value: '3.6000000001' } });
		await fireEvent.click(within(modal).getByRole('button', { name: '저장' }));
		const key = `${kind === 'realtime' ? 'realtime' : 'audio'}_${kind === 'tts' ? 'output' : 'input'}_per_hour`;
		await waitFor(() => expect(mocks.patch.mock.calls[0][1]).toEqual({ media_pricing: { ...legacy, [key]: '3.6000000001' } }));
		await waitFor(() => expect(screen.queryByRole('dialog', { name: '모델 가격 수정' })).toBeNull());
		const reopened = await openEditor();
		expect((within(reopened).getByLabelText(`${direction} 시간 단위`) as HTMLSelectElement).value).toBe('hour');
		expect((within(reopened).getByLabelText(`${direction} 시간 단가`) as HTMLInputElement).value).toBe('3.6000000001');
	});
	it('stores session-hour basis separately, keeping PCM and token rates when switching bases', async () => {
		const pricing = { realtime_input_per_minute: '0.01', realtime_output_per_minute: '0.02', token_rates: { audio: { input_per_million: '4' } } };
		rows = [model('realtime', pricing)]; render(ModelPage);
		const modal = await openEditor();
		await fireEvent.change(within(modal).getByLabelText('실시간 음성 과금 기준'), { target: { value: 'session' } });
		await fireEvent.change(within(modal).getByLabelText('세션 시간 단위'), { target: { value: 'hour' } });
		await fireEvent.input(within(modal).getByLabelText('세션 시간 단가'), { target: { value: '3.00' } });
		await fireEvent.click(within(modal).getByRole('button', { name: '저장' }));
		await waitFor(() => expect(mocks.patch.mock.calls[0][1]).toEqual({ media_pricing: { ...pricing, billing_basis: 'session', realtime_session_per_hour: '3.00' } }));
	});
	it.each(['token', 'projectId'])('discards a pending price completion after %s ownership changes', async (field) => {
		rows = [model('image', { image_per_unit: '0.04' })]; render(ModelPage);
		const modal = await openEditor();
		const pending = Promise.withResolvers<unknown>(); mocks.patch.mockReturnValue(pending.promise);
		await fireEvent.input(within(modal).getByLabelText('이미지 기본 단가'), { target: { value: '0.08' } });
		await fireEvent.click(within(modal).getByRole('button', { name: '저장' }));
		await waitFor(() => expect(mocks.patch).toHaveBeenCalledTimes(1));
		mocks.scope = { ...mocks.scope, [field]: 'other-owner' };
		for (const listener of mocks.listeners) listener(mocks.scope);
		await waitFor(() => expect(screen.queryByRole('dialog', { name: '모델 가격 수정' })).toBeNull());
		pending.resolve({});
		await Promise.resolve(); await Promise.resolve();
		expect(mocks.success).not.toHaveBeenCalled();
		expect(mocks.patch).toHaveBeenCalledWith('/api/v1/chat/admin/models/1', { media_pricing: { image_per_unit: '0.08' } }, 'token', 'project');
	});
});
