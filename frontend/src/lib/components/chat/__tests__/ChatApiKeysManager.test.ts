import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';

const mocks = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, patch: mocks.patch },
	ApiError: class ApiError extends Error {}
}));

import ChatApiKeysManager from '../ChatApiKeysManager.svelte';

const discovery = {
	endpoints: {
		openai: { sdk_base_url: 'https://inference.example/tenant/v1' },
		anthropic: { sdk_base_url: 'https://inference.example/tenant' }
	}
};

const apiKey = {
	id: 17,
	name: '내 CLI',
	key_prefix: 'lm_test',
	scopes: ['chat'],
	is_active: true,
	last_used_at: null,
	created_at: '2026-09-09T00:00:00Z',
	revoked_at: null,
	owner_monthly_credit_limit: null,
	admin_monthly_credit_limit: null,
	system_monthly_credit_limit: '1000',
	effective_monthly_credit_limit: '1000',
	month_credited_cost: '12.5',
	owner_weekly_credit_limit: null,
	system_weekly_credit_limit: '0',
	effective_weekly_credit_limit: '1000',
	week_credited_cost: '3.25'
};

function examples(container: HTMLElement): string {
	return Array.from(container.querySelectorAll('pre code'), (code) => code.textContent).join('\n');
}

describe('ChatApiKeysManager connection guide', () => {
	beforeEach(() => {
		vi.resetAllMocks();
		auth.set({
			token: 'browser-token', refreshToken: null, accessExpiresAt: null,
			userId: 'user-1', username: 'tester', projectId: 'project-1', projectName: 'Project',
			availableProjects: [], roles: [], isSystemAdmin: false, federated: false
		});
		mocks.patch.mockResolvedValue({});
		mocks.get.mockImplementation((path: string) => Promise.resolve(
			path.endsWith('/compat') ? discovery : path.endsWith('/api-keys') ? [apiKey] : []
		));
	});

	afterEach(cleanup);

	it('uses discovered SDK URLs verbatim instead of guessing from the dashboard host', async () => {
		const { container } = render(ChatApiKeysManager);
		await waitFor(() => expect(examples(container)).toContain('https://inference.example/tenant/v1'));
		const snippets = Array.from(container.querySelectorAll('pre code'), (code) => code.textContent!);
		expect(snippets[0]).toContain('base_url="https://inference.example/tenant/v1"');
		expect(snippets[1]).toContain('base_url="https://inference.example/tenant"');
		expect(examples(container)).not.toContain('api.localhost');
		expect(examples(container)).not.toContain('messages=[...]');
		expect(screen.getAllByRole('button', { name: '예제 복사' })).toHaveLength(2);
		expect(snippets[0]).toContain('{"provider": os.environ["LUMEN_PROVIDER"]}');
		expect(snippets[1]).toContain('{"provider": os.environ["LUMEN_PROVIDER"]}');
		expect(screen.getByText(/동일한 API ID가 여러 프로바이더에 등록된 경우에만/)).toBeTruthy();
	});

	it('copies each complete SDK example directly', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', {
			configurable: true,
			value: { writeText }
		});
		render(ChatApiKeysManager);
		await waitFor(() => expect(screen.getAllByRole('button', { name: '예제 복사' })).toHaveLength(2));

		await fireEvent.click(screen.getAllByRole('button', { name: '예제 복사' })[0]);

		expect(writeText).toHaveBeenCalledWith(expect.stringContaining('from openai import OpenAI'));
		expect(writeText).toHaveBeenCalledWith(expect.stringContaining('client.chat.completions.create'));
	});

	it('keeps key management available but hides examples until discovery retry succeeds', async () => {
		let unavailable = true;
		mocks.get.mockImplementation((path: string) => {
			if (path.endsWith('/compat')) return unavailable ? Promise.reject(new Error('offline')) : Promise.resolve(discovery);
			return Promise.resolve([]);
		});
		const { container } = render(ChatApiKeysManager);
		await screen.findByRole('alert');
		expect(container.querySelector('pre')).toBeNull();
		expect(screen.getByRole('button', { name: '+ 새 API 키 발급' })).toBeTruthy();
		unavailable = false;
		await fireEvent.click(screen.getByRole('button', { name: '연결 정보 다시 불러오기' }));
		await waitFor(() => expect(examples(container)).toContain(discovery.endpoints.openai.sdk_base_url));
		expect(screen.queryByRole('alert')).toBeNull();
	});

	it('does not publish code with a malformed or credential-bearing discovery URL', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/compat') ? {
			endpoints: {
				openai: { sdk_base_url: 'https://user:password@inference.example/v1' },
				anthropic: discovery.endpoints.anthropic
			}
		} : []));
		const { container } = render(ChatApiKeysManager);
		await screen.findByRole('alert');
		expect(container.querySelector('pre')).toBeNull();
		expect(container.textContent).not.toContain('user:password');
	});

	it('does not replace the current project endpoint with a late response from the previous project', async () => {
		let resolvePrevious!: (value: typeof discovery) => void;
		const previous = new Promise<typeof discovery>((resolve) => { resolvePrevious = resolve; });
		mocks.get.mockImplementation((path: string, _token: string, project: string) => {
			if (!path.endsWith('/compat')) return Promise.resolve([]);
			return project === 'project-1' ? previous : Promise.resolve(discovery);
		});
		const { container } = render(ChatApiKeysManager);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/compat', 'browser-token', 'project-1'));
		auth.update((state) => ({ ...state, projectId: 'project-2' }));
		await waitFor(() => expect(examples(container)).toContain(discovery.endpoints.openai.sdk_base_url));
		resolvePrevious({ endpoints: {
			openai: { sdk_base_url: 'https://previous.example/v1' },
			anthropic: { sdk_base_url: 'https://previous.example' }
		} });
		await previous;
		await tick();
		expect(examples(container)).toContain(discovery.endpoints.openai.sdk_base_url);
		expect(examples(container)).not.toContain('previous.example');
	});

	it('renames an active API key in place', async () => {
		render(ChatApiKeysManager);

		await fireEvent.click(await screen.findByRole('button', { name: '이름 변경' }));
		const input = screen.getByRole('textbox', { name: 'API 키 이름' });
		await fireEvent.input(input, { target: { value: '새 이름' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));

		await waitFor(() => {
			expect(mocks.patch).toHaveBeenCalledWith(
				'/api/v1/chat/api-keys/17',
				{ name: '새 이름' },
				'browser-token',
				'project-1'
			);
		});
	});

	it('rejects limits above the user quota and saves valid nullable limits', async () => {
		render(ChatApiKeysManager);

		await fireEvent.click(await screen.findByRole('button', { name: '한도 설정' }));
		const monthly = screen.getByLabelText('월 한도(크레딧)');
		const weekly = screen.getByLabelText('주간 한도(크레딧)');
		await fireEvent.input(monthly, { target: { value: '2000' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));

		expect(screen.getByText('사용자 쿼터(1,000)를 초과할 수 없습니다')).toBeTruthy();
		expect(mocks.patch).not.toHaveBeenCalled();

		await fireEvent.input(monthly, { target: { value: '500' } });
		await fireEvent.input(weekly, { target: { value: '' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));

		await waitFor(() => {
			expect(mocks.patch).toHaveBeenCalledWith(
				'/api/v1/chat/api-keys/17/limits',
				{ monthly_credit_limit: '500', weekly_credit_limit: null },
				'browser-token',
				'project-1'
			);
		});
	});

	it('blocks a limit above the administrator ceiling before sending a request', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(
			path.endsWith('/compat')
				? discovery
				: path.endsWith('/api-keys')
					? [{ ...apiKey, admin_monthly_credit_limit: '500', effective_monthly_credit_limit: '500' }]
					: []
		));
		render(ChatApiKeysManager);

		await fireEvent.click(await screen.findByRole('button', { name: '한도 설정' }));
		await fireEvent.input(screen.getByLabelText('월 한도(크레딧)'), { target: { value: '800' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));

		expect(screen.getByText('관리자 한도(500)를 초과할 수 없습니다')).toBeTruthy();
		expect(mocks.patch).not.toHaveBeenCalled();
	});
});
