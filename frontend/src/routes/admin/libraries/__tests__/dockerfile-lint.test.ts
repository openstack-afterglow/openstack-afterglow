import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { DockerfileLintResponse } from '$lib/components/admin/libraries/DockerfileLintPanel.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error { status = 500; } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }) }));
import Page from '../+page.svelte';

const lintPath = '/api/v1/palimpsest/builds/dockerfile/lint';
const lintCalls = () => mocks.post.mock.calls.filter(([path]) => path === lintPath);
const image = { id: 'image-24', name: 'ubuntu:24.04', ubuntu_base: 'ubuntu-24.04', min_disk: 0, visibility: 'public' };
const valid: DockerfileLintResponse = {
	valid: true, diagnostics: [], warnings: [],
	from: { line: 1, ref: 'ubuntu:24.04', kind: 'ubuntu_tag', image, parent: null, completions: [], error: null, note: null },
	layers: { new: 3, inherited: 0, total: 3, limit: 25, by_instruction: { RUN: 1, ENV: 1, WORKDIR: 1 } },
};
const invalid: DockerfileLintResponse = {
	...valid, valid: false, diagnostics: [{ line: 2, message: 'COPY에는 빌드 컨텍스트가 필요합니다.' }],
};

beforeEach(() => {
	vi.clearAllMocks();
	vi.useFakeTimers();
	mocks.get.mockImplementation(async (path: string) => path.endsWith('/base-images') ? [image] : []);
	mocks.post.mockImplementation(async (path: string) => path === lintPath ? valid : {});
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

async function studio() {
	render(Page);
	await vi.waitFor(() => expect(screen.getByRole('textbox', { name: /Dockerfile 본문/ })).toBeTruthy());
	const editor = screen.getByRole('textbox', { name: /Dockerfile 본문/ });
	const panel = screen.getByRole('region', { name: 'Dockerfile 검사' });
	await vi.advanceTimersByTimeAsync(600);
	await vi.waitFor(() => expect(within(panel).getByText('문법 OK · 레이어 3개')).toBeTruthy());
	return { editor, panel };
}

describe('administrator Dockerfile lint', () => {
	it('debounces text and prefix edits for 600ms, reports diagnostics, and gates plan/build', async () => {
		const { editor, panel } = await studio();
		mocks.post.mockClear();
		mocks.post.mockImplementation(async (path: string) => path === lintPath ? invalid : {});
		await fireEvent.input(editor, { target: { value: 'FROM ubuntu:24.04\nRUN echo hi' } });
		await vi.advanceTimersByTimeAsync(400);
		await fireEvent.input(editor, { target: { value: 'FROM ubuntu:24.04\nCOPY . /app' } });
		await fireEvent.input(screen.getByLabelText('Layer prefix *'), { target: { value: 'sample' } });
		await vi.advanceTimersByTimeAsync(599);
		expect(lintCalls()).toHaveLength(0);
		await vi.advanceTimersByTimeAsync(1);
		await vi.waitFor(() => expect(within(panel).getByText('오류 1개')).toBeTruthy());
		expect(lintCalls()).toHaveLength(1);
		expect(lintCalls()[0][1]).toEqual({ dockerfile: 'FROM ubuntu:24.04\nCOPY . /app', layer_prefix: 'sample' });
		expect(within(panel).getByText('L2')).toBeTruthy();
		expect(within(panel).getByText(/COPY에는 빌드 컨텍스트가 필요합니다/)).toBeTruthy();
		expect(screen.getByRole('button', { name: '빌드 계획 미리보기' }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByRole('button', { name: 'Dockerfile 빌드 시작' }).hasAttribute('disabled')).toBe(true);
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});

	it('ignores stale responses when text, prefix or mode changes', async () => {
		const { editor, panel } = await studio();
		const stale = Promise.withResolvers<DockerfileLintResponse>();
		mocks.post.mockClear();
		mocks.post.mockImplementation((path: string) => path === lintPath ? stale.promise : Promise.resolve({}));
		await fireEvent.input(editor, { target: { value: 'FROM ubuntu:24.04\nCOPY old /app' } });
		await vi.advanceTimersByTimeAsync(600);
		expect(lintCalls()).toHaveLength(1);
		await fireEvent.input(screen.getByLabelText('Layer prefix *'), { target: { value: 'new-prefix' } });
		stale.resolve(invalid);
		await stale.promise;
		expect(within(panel).queryByText('오류 1개')).toBeNull();
		mocks.post.mockImplementation(async (path: string) => path === lintPath ? valid : {});
		await vi.advanceTimersByTimeAsync(600);
		await vi.waitFor(() => expect(within(panel).getByText('문법 OK · 레이어 3개')).toBeTruthy());
		expect(lintCalls()[1][1]).toEqual({ dockerfile: 'FROM ubuntu:24.04\nCOPY old /app', layer_prefix: 'new-prefix' });
		const later = Promise.withResolvers<DockerfileLintResponse>();
		mocks.post.mockImplementation((path: string) => path === lintPath ? later.promise : Promise.resolve({}));
		await fireEvent.input(editor, { target: { value: 'FROM ubuntu:24.04\nRUN echo replacement' } });
		await vi.advanceTimersByTimeAsync(600);
		await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 입력 방식' })).getByRole('button', { name: 'GitHub 커밋' }));
		expect(screen.queryByRole('region', { name: 'Dockerfile 검사' })).toBeNull();
		later.resolve(invalid);
		await later.promise;
		await vi.advanceTimersByTimeAsync(600);
		expect(lintCalls()).toHaveLength(3);
		mocks.post.mockImplementation(async (path: string) => path === lintPath ? valid : {});
		await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 입력 방식' })).getByRole('button', { name: '직접 작성' }));
		await vi.advanceTimersByTimeAsync(600);
		await vi.waitFor(() => expect(within(screen.getByRole('region', { name: 'Dockerfile 검사' })).getByText('문법 OK · 레이어 3개')).toBeTruthy());
	});

	it('discards a late diagnostic after the text changes and clears lint on empty input', async () => {
		const { editor, panel } = await studio();
		const old = Promise.withResolvers<DockerfileLintResponse>();
		mocks.post.mockClear();
		mocks.post.mockImplementation((path: string, body: { dockerfile: string }) => path === lintPath && body.dockerfile.includes('COPY') ? old.promise : Promise.resolve(valid));
		await fireEvent.input(editor, { target: { value: 'FROM ubuntu:24.04\nCOPY old /app' } });
		await vi.advanceTimersByTimeAsync(600);
		await fireEvent.input(editor, { target: { value: 'FROM ubuntu:24.04\nRUN echo replacement' } });
		old.resolve(invalid);
		await old.promise;
		expect(within(panel).queryByText('오류 1개')).toBeNull();
		await vi.advanceTimersByTimeAsync(600);
		await vi.waitFor(() => expect(within(panel).getByText('문법 OK · 레이어 3개')).toBeTruthy());
		expect(lintCalls()).toHaveLength(2);
		await fireEvent.input(editor, { target: { value: '' } });
		expect(within(panel).getByText('Dockerfile을 입력하면 자동으로 검사합니다.')).toBeTruthy();
		expect(within(panel).queryByText('문법 OK · 레이어 3개')).toBeNull();
	});

	it('allows plan and build after lint transport failure while omitting base_image_id everywhere', async () => {
		const { editor, panel } = await studio();
		await fireEvent.input(screen.getByLabelText('Layer prefix *'), { target: { value: 'sample' } });
		mocks.post.mockRejectedValueOnce(new Error('offline'));
		await fireEvent.input(editor, { target: { value: 'FROM ubuntu:24.04\nRUN echo hello' } });
		await vi.advanceTimersByTimeAsync(600);
		await vi.waitFor(() => expect(within(panel).getByText('검사 실패')).toBeTruthy());
		expect(within(panel).getByText(/네트워크 오류/)).toBeTruthy();
		expect(screen.getByRole('button', { name: '빌드 계획 미리보기' }).hasAttribute('disabled')).toBe(false);
		expect(screen.getByRole('button', { name: 'Dockerfile 빌드 시작' }).hasAttribute('disabled')).toBe(false);
		mocks.post.mockImplementation(async (path: string) => path.endsWith('/plan') ? {
			source_type: 'inline_dockerfile', dockerfile_digest: 'sha256:12345678901234567890', parent_digest: null,
			ubuntu_base: 'ubuntu-24.04', cached_artifact_ids: [], steps: [],
		} : path === lintPath ? valid : { id: 123, profile_name: 'sample' });
		await fireEvent.click(screen.getByRole('button', { name: '빌드 계획 미리보기' }));
		await vi.waitFor(() => expect(screen.getByText('빌드 계획 (미리보기)')).toBeTruthy());
		await fireEvent.click(screen.getByRole('button', { name: 'Dockerfile 빌드 시작' }));
		await vi.waitFor(() => expect(screen.getByText(/Palimpsest Dockerfile 빌드 시작 \(ID: 123/)).toBeTruthy());
		for (const [path, body] of mocks.post.mock.calls) {
			if (path === lintPath || path.endsWith('/plan') || path === '/api/v1/palimpsest/builds/dockerfile') expect(body).not.toHaveProperty('base_image_id');
		}
		await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 입력 방식' })).getByRole('button', { name: 'GitHub 커밋' }));
		await fireEvent.input(screen.getByLabelText('GitHub URL *'), { target: { value: 'https://github.com/example/repo' } });
		await fireEvent.click(screen.getByRole('button', { name: 'GitHub Dockerfile import 시작' }));
		await vi.waitFor(() => expect(mocks.post.mock.calls.some(([path]) => path === '/api/v1/admin/libraries/imports/dockerfile')).toBe(true));
		expect(mocks.post.mock.calls.find(([path]) => path === '/api/v1/admin/libraries/imports/dockerfile')?.[1]).not.toHaveProperty('base_image_id');
		expect(screen.queryByLabelText(/Glance base image override/)).toBeNull();
		expect(screen.getAllByLabelText('Glance base image *')).toHaveLength(2);
	});

	it('lints template, fetched URL and uploaded file content through the same editor', async () => {
		await studio();
		mocks.post.mockClear();
		await fireEvent.click(screen.getByRole('button', { name: 'Python 3.12' }));
		await vi.advanceTimersByTimeAsync(600);
		expect(lintCalls().at(-1)?.[1].dockerfile).toContain('RUN pip install');
		await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 입력 방식' })).getByRole('button', { name: 'URL 가져오기' }));
		await fireEvent.input(screen.getByLabelText('Dockerfile URL *'), { target: { value: 'https://example.com/Dockerfile' } });
		mocks.post.mockImplementation(async (path: string) => path.endsWith('/fetch-url')
			? { dockerfile: 'FROM ubuntu:24.04\nRUN echo fetched', filename: 'Dockerfile', size_bytes: 36, url: 'https://example.com/Dockerfile' }
			: valid);
		await fireEvent.click(screen.getByRole('button', { name: '가져오기' }));
		await vi.waitFor(() => expect((screen.getByRole('textbox', { name: /Dockerfile 본문/ }) as HTMLTextAreaElement).value).toContain('RUN echo fetched'));
		await vi.advanceTimersByTimeAsync(600);
		expect(lintCalls().at(-1)?.[1].dockerfile).toContain('RUN echo fetched');
		await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 입력 방식' })).getByRole('button', { name: '파일 업로드' }));
		await fireEvent.change(screen.getByLabelText('로컬 Dockerfile 선택 *'), { target: { files: [new File(['FROM ubuntu:24.04\nRUN echo uploaded'], 'Dockerfile', { type: 'text/plain' })] } });
		await vi.waitFor(() => expect((screen.getByRole('textbox', { name: /Dockerfile 본문/ }) as HTMLTextAreaElement).value).toContain('RUN echo uploaded'));
		await vi.advanceTimersByTimeAsync(600);
		expect(lintCalls().at(-1)?.[1].dockerfile).toContain('RUN echo uploaded');
	});
});
