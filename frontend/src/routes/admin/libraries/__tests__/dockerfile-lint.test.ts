import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import { page } from '$app/stores';
import type { DockerfileLintResponse } from '$lib/components/admin/libraries/DockerfileLintPanel.svelte';
import { auth } from '$lib/stores/auth';
import { defaultUsageDraft, toLocalDateTime } from '$lib/utils/instanceUsage';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error { status = 500; } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project' }),
	authReady: writable(false),
	logoutInProgress: writable(false),
	projectSwitching: writable(false),
}));
vi.mock('$app/stores', () => ({ page: writable({ data: {}, url: new URL('http://localhost/admin/libraries'), state: {} }) }));
vi.mock('$app/navigation', () => ({ goto: async (url: string) => { routePage.update(value => ({ ...value, url: new URL(url, 'http://localhost') })); } }));
import Page from '../+page.svelte';
const routePage = page as unknown as Writable<{ data: Record<string, never>; url: URL; state: Record<string, never> }>;

const lintPath = '/api/v1/palimpsest/builds/dockerfile/lint';
const lintCalls = () => mocks.post.mock.calls.filter(([path]) => path === lintPath);
const image = { id: 'image-24', name: 'ubuntu:24.04', status: 'active', ubuntu_base: 'ubuntu-24.04', min_disk: 0, visibility: 'public' };
const consumerFlavors = [
    { id: 'flavor-a', name: 'Small CPU', vcpus: 2, ram: 4096, usage_schedule_required: false },
    { id: 'flavor-gpu', name: 'Training GPU', vcpus: 4, ram: 8192, is_gpu: true, usage_schedule_required: true },
    { id: 'flavor-large', name: 'Large CPU', vcpus: 12, ram: 32768 },
];
const defaultSchedule = { expires_at: null, expiry_action: 'shelve', delete_volumes: false, reason: '' };
async function chooseConsumerFlavor(label: string, name: string) {
    await fireEvent.click(screen.getByLabelText(label));
    await fireEvent.click(screen.getByRole('option', { name: new RegExp(name) }));
}
const valid: DockerfileLintResponse = {
	valid: true, diagnostics: [], warnings: [],
	from: { line: 1, ref: 'ubuntu:24.04', kind: 'ubuntu_tag', image, parent: null, completions: [], error: null, note: null },
	layers: { new: 3, inherited: 0, total: 3, limit: 25, by_instruction: { RUN: 1, ENV: 1, WORKDIR: 1 } },
};
const invalid: DockerfileLintResponse = {
	...valid, valid: false, diagnostics: [{ line: 2, message: 'COPY에는 빌드 컨텍스트가 필요합니다.' }],
};
const fromOnly: DockerfileLintResponse = {
    ...valid, valid: false,
    diagnostics: [{ line: null, message: 'Dockerfile에는 layer로 변환할 RUN/COPY/ADD/ENV/WORKDIR instruction이 필요합니다' }],
    layers: { new: 0, inherited: 0, total: 0, limit: 25, by_instruction: {} },
};

beforeEach(() => {
	vi.clearAllMocks();
	vi.useFakeTimers();
    routePage.set({ data: {}, url: new URL('http://localhost/admin/libraries'), state: {} });
	mocks.get.mockImplementation(async (path: string) => path === '/api/v1/flavors' ? consumerFlavors : path.endsWith('/base-images') ? [image] : []);
    mocks.post.mockImplementation(async (path: string, body: { dockerfile?: string }) => path === lintPath
        ? (/^FROM[^\r\n]*(?:\r?\n)?$/i.test(body.dockerfile ?? '') ? fromOnly : valid) : {});
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

async function studio() {
	render(Page);
    await vi.waitFor(() => expect(screen.getByRole('button', { name: '빌드 만들기' })).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: '빌드 만들기' }));
    await vi.waitFor(() => expect(screen.getByRole('button', { name: '기존 Dockerfile' })).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: '기존 Dockerfile' }));
    await fireEvent.click(screen.getByRole('button', { name: '편집기로 계속' }));
	await vi.waitFor(() => expect(screen.getByRole('textbox', { name: /Dockerfile 본문/ })).toBeTruthy());
	const editor = screen.getByRole('textbox', { name: /Dockerfile 본문/ });
    await fireEvent.input(editor, { target: { value: 'FROM ubuntu:24.04\nRUN apt-get update && apt-get install -y curl git\nENV APP_ENV=production\nWORKDIR /app\n' } });
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
        expect(mocks.post).toHaveBeenCalledWith('/api/v1/palimpsest/builds/dockerfile', {
            dockerfile: 'FROM ubuntu:24.04\nRUN echo hello', layer_prefix: 'sample',
        }, 'token', 'project');
		for (const [path, body] of mocks.post.mock.calls) {
			if (path === lintPath || path.endsWith('/plan') || path === '/api/v1/palimpsest/builds/dockerfile') expect(body).not.toHaveProperty('base_image_id');
		}
		await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 입력 방식' })).getByRole('button', { name: 'GitHub 커밋' }));
        await fireEvent.input(screen.getByLabelText('GitHub URL *'), { target: { value: 'https://github.com/example/repo' } });
        const importButton = screen.getByRole('button', { name: 'GitHub Dockerfile import 시작' });
        expect(importButton.hasAttribute('disabled')).toBe(true);
        await fireEvent.input(screen.getByLabelText('Commit SHA *'), { target: { value: 'main' } });
        expect(importButton.hasAttribute('disabled')).toBe(true);
        await fireEvent.input(screen.getByLabelText('Commit SHA *'), { target: { value: 'a'.repeat(40) } });
        await fireEvent.click(importButton);
        await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/libraries/imports/dockerfile', {
            github_url: 'https://github.com/example/repo', ref: 'a'.repeat(40), dockerfile_path: 'Dockerfile', layer_prefix: 'sample',
        }, 'token', 'project'));
        expect(screen.queryByLabelText(/Glance base image/)).toBeNull();
	});

    it('imports URL and uploaded content into the same Dockerfile build action', async () => {
        await studio();
        mocks.post.mockClear();
		await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 입력 방식' })).getByRole('button', { name: 'URL 가져오기' }));
		await fireEvent.input(screen.getByLabelText('Dockerfile URL *'), { target: { value: 'https://example.com/Dockerfile' } });
		mocks.post.mockImplementation(async (path: string) => path.endsWith('/fetch-url')
			? { dockerfile: 'FROM ubuntu:24.04\nRUN echo fetched', filename: 'Dockerfile', size_bytes: 36, url: 'https://example.com/Dockerfile' }
            : path === lintPath ? valid : { id: 123, profile_name: 'custom-layer' });
		await fireEvent.click(screen.getByRole('button', { name: '가져오기' }));
		await vi.waitFor(() => expect((screen.getByRole('textbox', { name: /Dockerfile 본문/ }) as HTMLTextAreaElement).value).toContain('RUN echo fetched'));
		await vi.advanceTimersByTimeAsync(600);
		expect(lintCalls().at(-1)?.[1].dockerfile).toContain('RUN echo fetched');
        await fireEvent.click(screen.getByRole('button', { name: 'Dockerfile 빌드 시작' }));
        await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/palimpsest/builds/dockerfile', {
            dockerfile: 'FROM ubuntu:24.04\nRUN echo fetched', layer_prefix: 'custom-layer',
        }, 'token', 'project'));
		await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 입력 방식' })).getByRole('button', { name: '파일 업로드' }));
		await fireEvent.change(screen.getByLabelText('로컬 Dockerfile 선택 *'), { target: { files: [new File(['FROM ubuntu:24.04\nRUN echo uploaded'], 'Dockerfile', { type: 'text/plain' })] } });
		await vi.waitFor(() => expect((screen.getByRole('textbox', { name: /Dockerfile 본문/ }) as HTMLTextAreaElement).value).toContain('RUN echo uploaded'));
		await vi.advanceTimersByTimeAsync(600);
		expect(lintCalls().at(-1)?.[1].dockerfile).toContain('RUN echo uploaded');
        await fireEvent.click(screen.getByRole('button', { name: 'Dockerfile 빌드 시작' }));
        await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/palimpsest/builds/dockerfile', {
            dockerfile: 'FROM ubuntu:24.04\nRUN echo uploaded', layer_prefix: 'custom-layer',
        }, 'token', 'project'));
        expect(mocks.post.mock.calls.some(([path]) => path === '/api/v1/admin/libraries/build')).toBe(false);
	});
    it('does not replace edited Dockerfile text when a URL fetch or file read resolves late', async () => {
        await studio();
        const pending = Promise.withResolvers<{ dockerfile: string; url: string; filename: string; size_bytes: number }>();
        mocks.post.mockImplementation((path: string) => path.endsWith('/fetch-url') ? pending.promise : Promise.resolve(valid));
        const modes = screen.getByRole('group', { name: 'Dockerfile 입력 방식' });
        await fireEvent.click(within(modes).getByRole('button', { name: 'URL 가져오기' }));
        await fireEvent.input(screen.getByLabelText('Dockerfile URL *'), { target: { value: 'https://example.com/old' } });
        await fireEvent.click(screen.getByRole('button', { name: '가져오기' }));
        await fireEvent.click(within(modes).getByRole('button', { name: '직접 작성' }));
        await fireEvent.input(screen.getByRole('textbox', { name: /Dockerfile 본문/ }), { target: { value: 'FROM ubuntu:24.04\nRUN echo edited' } });
        pending.resolve({ dockerfile: 'FROM ubuntu:24.04\nRUN echo old', url: 'https://example.com/old', filename: 'Dockerfile', size_bytes: 35 });
        await pending.promise;
        expect((screen.getByRole('textbox', { name: /Dockerfile 본문/ }) as HTMLTextAreaElement).value).toContain('RUN echo edited');
        expect(screen.queryByText(/성공적으로 불러왔습니다/)).toBeNull();

        const readers: Array<{ onload: ((event: { target: { result: string } }) => void) | null }> = [];
        class DeferredReader {
            onload: ((event: { target: { result: string } }) => void) | null = null;
            onerror: (() => void) | null = null;
            readAsText() { readers.push(this); }
        }
        vi.stubGlobal('FileReader', DeferredReader);
        await fireEvent.click(within(modes).getByRole('button', { name: '파일 업로드' }));
        await fireEvent.change(screen.getByLabelText('로컬 Dockerfile 선택 *'), {
            target: { files: [new File(['FROM ubuntu:24.04\nRUN echo uploaded'], 'Dockerfile')] },
        });
        expect(readers).toHaveLength(1);
        await fireEvent.click(within(modes).getByRole('button', { name: '직접 작성' }));
        await fireEvent.input(screen.getByRole('textbox', { name: /Dockerfile 본문/ }), { target: { value: 'FROM ubuntu:24.04\nRUN echo final' } });
        readers[0].onload?.({ target: { result: 'FROM ubuntu:24.04\nRUN echo uploaded' } });
        expect((screen.getByRole('textbox', { name: /Dockerfile 본문/ }) as HTMLTextAreaElement).value).toContain('RUN echo final');
        expect(screen.queryByText(/로컬 파일 .*불러왔습니다/)).toBeNull();
    });
    it('discards a deferred file completion across same-tick owner ABA', async () => {
        await studio();
        const readers: Array<{ onload: ((event: { target: { result: string } }) => void) | null }> = [];
        class DeferredReader {
            onload: ((event: { target: { result: string } }) => void) | null = null;
            onerror: (() => void) | null = null;
            readAsText() { readers.push(this); }
        }
        vi.stubGlobal('FileReader', DeferredReader);
        await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 입력 방식' })).getByRole('button', { name: '파일 업로드' }));
        await fireEvent.change(screen.getByLabelText('로컬 Dockerfile 선택 *'), {
            target: { files: [new File(['FROM old-owner\nRUN echo old-owner'], 'Dockerfile')] },
        });
        expect(readers).toHaveLength(1);
        auth.update(state => ({ ...state, projectId: 'other-project' }));
        auth.update(state => ({ ...state, projectId: 'project' }));
        await vi.advanceTimersByTimeAsync(0);
        readers[0].onload?.({ target: { result: 'FROM old-owner\nRUN echo old-owner' } });
        await vi.advanceTimersByTimeAsync(0);
        expect(screen.queryByText(/로컬 파일 .*불러왔습니다/)).toBeNull();
        await fireEvent.click(screen.getByRole('button', { name: '기존 Dockerfile' }));
        await fireEvent.click(screen.getByRole('button', { name: '편집기로 계속' }));
        await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 입력 방식' })).getByRole('button', { name: '직접 작성' }));
        expect((screen.getByRole('textbox', { name: /Dockerfile 본문/ }) as HTMLTextAreaElement).value).toBe('');
    });

    it('opens discovery without an unsolicited lint and navigates each historical workspace', async () => {
        render(Page);
        await vi.advanceTimersByTimeAsync(600);
        expect(lintCalls()).toHaveLength(0);
        expect(screen.queryByRole('textbox', { name: /Dockerfile 본문/ })).toBeNull();
        for (const name of ['프로필', '아티팩트', '빌드 기록', '인스턴스', '레이어 카탈로그']) {
            await fireEvent.click(screen.getByRole('tab', { name }));
            expect(screen.getByRole('tab', { name }).getAttribute('aria-selected')).toBe('true');
        }
        await fireEvent.click(screen.getByRole('tab', { name: '빌드 스튜디오' }));
        expect(screen.getByRole('button', { name: '편집기로 계속' }).hasAttribute('disabled')).toBe(true);
        expect(lintCalls()).toHaveLength(0);
        await fireEvent.click(screen.getByLabelText('활성 기반 이미지를 선택하세요'));
        await fireEvent.click(screen.getByRole('option', { name: /ubuntu:24.04/ }));
        await fireEvent.click(screen.getByRole('button', { name: '편집기로 계속' }));
        await vi.waitFor(() => expect((screen.getByRole('textbox', { name: /Dockerfile 본문/ }) as HTMLTextAreaElement).value).toBe('FROM image-24\n'));
        expect(lintCalls()[0][1]).toEqual({ dockerfile: 'FROM image-24\n' });
        await vi.advanceTimersByTimeAsync(600);
        expect(screen.getByText(fromOnly.diagnostics[0].message)).toBeTruthy();
        expect(screen.getByRole('button', { name: 'Dockerfile 빌드 시작' }).hasAttribute('disabled')).toBe(true);
        routePage.update(value => ({ ...value, url: new URL('http://localhost/admin/libraries?tab=profiles') }));
        await vi.advanceTimersByTimeAsync(0);
        expect(screen.queryByRole('textbox', { name: /Dockerfile 본문/ })).toBeNull();
        routePage.update(value => ({ ...value, url: new URL('http://localhost/admin/libraries?tab=studio&step=editor') }));
        await vi.waitFor(() => expect((screen.getByRole('textbox', { name: /Dockerfile 본문/ }) as HTMLTextAreaElement).value).toBe('FROM image-24\n'));
        await fireEvent.input(screen.getByRole('textbox', { name: /Dockerfile 본문/ }), { target: { value: 'FROM old-image\nRUN echo retained\nENV KEEP=yes\nWORKDIR /workspace\n' } });
        await fireEvent.click(screen.getByRole('button', { name: '다른 기반 선택' }));
        await fireEvent.click(screen.getByRole('button', { name: '편집기로 계속' }));
        await vi.waitFor(() => expect((screen.getByRole('textbox', { name: /Dockerfile 본문/ }) as HTMLTextAreaElement).value).toBe('FROM image-24\nRUN echo retained\nENV KEEP=yes\nWORKDIR /workspace\n'));
        expect(lintCalls().some(([, body]) => body.dockerfile === 'FROM image-24\nRUN echo retained\nENV KEEP=yes\nWORKDIR /workspace\n')).toBe(true);
    });
    it('keeps genuine selected-source failures visible without opening the editor', async () => {
        render(Page);
        await vi.advanceTimersByTimeAsync(0);
        await fireEvent.click(screen.getByRole('tab', { name: '빌드 스튜디오' }));
        await fireEvent.click(screen.getByLabelText('활성 기반 이미지를 선택하세요'));
        await fireEvent.click(screen.getByRole('option', { name: /ubuntu:24.04/ }));
        mocks.post.mockResolvedValue({ ...fromOnly, from: { ...fromOnly.from, image: null, error: 'Selected Glance image is no longer active' } });
        await fireEvent.click(screen.getByRole('button', { name: '편집기로 계속' }));
        await vi.waitFor(() => expect(screen.getByText('Selected Glance image is no longer active')).toBeTruthy());
        expect(screen.queryByRole('textbox', { name: /Dockerfile 본문/ })).toBeNull();
        expect(mocks.post.mock.calls.some(([path]) => path === '/api/v1/palimpsest/builds/dockerfile')).toBe(false);
    });

    it.each([false, true])('resolves full native inventory and latest sealed profile version (rebuilt=%s)', async (rebuilt) => {
        const digest = `sha256:${'a'.repeat(64)}`, oldDigest = `sha256:${'b'.repeat(64)}`;
        const profile = { id: 4, name: 'training', layers: ['training-leaf', 'root'], is_published: false };
        const root = { id: 1, name: 'root', parent_id: null, is_sealed: true, blob_digest: oldDigest, digest_state: 'ready', created_at: '2026-01-01T00:00:00' };
        const old = { id: 9, name: 'training-leaf', parent_id: 1, is_sealed: true, blob_digest: rebuilt ? oldDigest : digest, digest_state: 'ready', created_at: '2026-01-02T00:00:00' };
        const newest = { ...old, id: 10, blob_digest: digest, created_at: '2026-01-03T00:00:00' };
        const recent = Array.from({ length: 100 }, (_, index) => ({ ...root, id: index + 100, name: `recent-${index}`, created_at: '2026-10-01T00:00:00' }));
        const full = [root, old, ...(rebuilt ? [newest, { ...newest, id: 11, is_sealed: false, created_at: '2026-01-04T00:00:00' }] : []), ...recent];
        const parentId = rebuilt ? 10 : 9;
        mocks.get.mockImplementation(async (path: string) => path === '/api/v1/admin/libraries/profiles'
            ? [profile] : path === '/api/v1/admin/libraries/profiles/training' ? profile
            : path === '/api/v1/admin/palimpsest/artifacts' ? full
            : path === '/api/v1/admin/libraries/artifacts' ? recent : []);
        mocks.post.mockResolvedValue({ ...fromOnly, from: { ...fromOnly.from, kind: 'palimpsest', image: null,
            parent: { id: parentId, name: 'training-leaf', blob_digest: digest, ubuntu_base: 'ubuntu-24.04', base_image_name: 'ubuntu:24.04', chain_depth: 2 } } });
        render(Page);
        await vi.advanceTimersByTimeAsync(0);
        await fireEvent.click(screen.getByRole('tab', { name: '빌드 스튜디오' }));
        await fireEvent.click(screen.getByRole('button', { name: '저장된 프로필' }));
        await fireEvent.click(screen.getByLabelText('저장된 프로필'));
        await fireEvent.click(screen.getByRole('option', { name: /training/ }));
        await fireEvent.click(screen.getByRole('button', { name: '편집기로 계속' }));
        await vi.waitFor(() => expect((screen.getByRole('textbox', { name: /Dockerfile 본문/ }) as HTMLTextAreaElement).value).toBe(`FROM palimpsest/training-leaf@${digest}\n`));
        expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/palimpsest/artifacts', 'token', 'project', expect.objectContaining({ cache: 'no-store', signal: expect.any(AbortSignal) }));
        expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/libraries/profiles/training', 'token', 'project', expect.objectContaining({ cache: 'no-store' }));
        expect(lintCalls()[0][1]).toEqual({ dockerfile: `FROM palimpsest/training-leaf@${digest}\n` });
        await vi.advanceTimersByTimeAsync(600);
        expect(screen.getByText(fromOnly.diagnostics[0].message)).toBeTruthy();
        expect(screen.getByRole('button', { name: 'Dockerfile 빌드 시작' }).hasAttribute('disabled')).toBe(true);
    });

    it('shows cache artifacts separately from remaining steps and discards stale plans', async () => {
        const { editor } = await studio();
        await fireEvent.input(screen.getByLabelText('Layer prefix *'), { target: { value: 'sample' } });
        await vi.advanceTimersByTimeAsync(600);
        const plan = { source_type: 'inline_dockerfile', dockerfile_digest: 'sha256:1234', parent_digest: null,
            ubuntu_base: 'ubuntu-24.04', cached_artifact_ids: [7], steps: [{ name: 'sample-run', instruction: 'RUN', args: 'echo new' }] };
        mocks.post.mockImplementation(async (path: string) => path.endsWith('/plan') ? plan : valid);
        await fireEvent.click(screen.getByRole('button', { name: '빌드 계획 미리보기' }));
        await vi.waitFor(() => expect(screen.getByText('캐시 재사용 artifact: #7')).toBeTruthy());
        expect(screen.getByText('신규 빌드')).toBeTruthy();
        const pending = Promise.withResolvers<typeof plan>();
        mocks.post.mockImplementation((path: string) => path.endsWith('/plan') ? pending.promise : Promise.resolve(valid));
        await fireEvent.click(screen.getByRole('button', { name: '빌드 계획 미리보기' }));
        await fireEvent.input(editor, { target: { value: 'FROM ubuntu:24.04\nRUN echo changed' } });
        pending.resolve(plan);
        await pending.promise;
        await vi.advanceTimersByTimeAsync(600);
        expect(screen.queryByText('빌드 계획 (미리보기)')).toBeNull();
    });

    it('selects historical jobs, follows progress and preserves records on refresh failure', async () => {
        let job = { id: 42, profile_name: 'historical', status: 'running', progress_step: 'RUN 실행', progress_pct: 35,
            error_message: null as string | null, github_url: 'https://github.com/example/repo', commit_sha: 'b'.repeat(40),
            dockerfile_path: 'Dockerfile', base_image_name: 'ubuntu:24.04', artifact_ids: [7], build_ids: [8], planned_layers: [],
            consume_id: 19, consumer_status: 'bootstrapping', consumer_spec: { flavor_id: 'flavor-1', server_name: 'auto-vm' } };
        mocks.get.mockImplementation(async (path: string) => path.endsWith('/imports') ? [job] : []);
        await studio();
        await fireEvent.click(screen.getByRole('tab', { name: '빌드 기록' }));
        await fireEvent.click(screen.getByRole('button', { name: '작업 #42 상세' }));
        const selected = screen.getByRole('region', { name: '선택한 Dockerfile 작업' });
        expect(within(selected).getByRole('progressbar').getAttribute('aria-valuenow')).toBe('35');
        expect(within(selected).getByText('Build: #8')).toBeTruthy();
        expect(within(selected).getByText(/소비 VM: #19 · bootstrapping \(auto-vm · flavor-1\)/)).toBeTruthy();
        job = { ...job, status: 'error', progress_pct: 60, error_message: 'builder failed' };
        await vi.advanceTimersByTimeAsync(10_000);
        expect(within(selected).getByRole('progressbar').getAttribute('aria-valuenow')).toBe('60');
        expect(within(selected).getByText('builder failed')).toBeTruthy();
        mocks.get.mockRejectedValue(new Error('offline'));
        await fireEvent.click(screen.getByRole('button', { name: '새로고침' }));
        await vi.waitFor(() => expect(screen.getByText(/작업 기록을 갱신하지 못했습니다/)).toBeTruthy());
        expect(screen.getByRole('button', { name: '작업 #42 상세' })).toBeTruthy();
    });
    it('keeps legacy import history visible without offering unsupported VM creation', async () => {
        const legacy = { id: 41, profile_name: 'legacy-profile', status: 'complete', progress_step: 'profile_saved', progress_pct: 100,
            dockerfile_digest: null, artifact_ids: [7], build_ids: [8], planned_layers: [], consumer_spec: null, consume_id: null };
        mocks.get.mockImplementation(async (path: string) => path.endsWith('/imports') ? [legacy] : []);
        await studio();
        await fireEvent.click(screen.getByRole('tab', { name: '빌드 기록' }));
        await fireEvent.click(screen.getByRole('button', { name: '작업 #41 상세' }));
        const selected = screen.getByRole('region', { name: '선택한 Dockerfile 작업' });
        expect(within(selected).getByText('Artifact: #7')).toBeTruthy();
        expect(within(selected).queryByRole('button', { name: '이 작업의 artifact로 VM 생성' })).toBeNull();
    });

    it('creates a VM from the selected completed job rather than the current profile', async () => {
        const job = { id: 42, profile_name: 'renamed-profile', status: 'complete', progress_step: '봉인 완료', progress_pct: 100,
            dockerfile_digest: 'sha256:1234', artifact_ids: [1, 3], build_ids: [5], planned_layers: [], consumer_spec: null, consume_id: null };
        mocks.get.mockImplementation(async (path: string) => path === '/api/v1/flavors' ? consumerFlavors : path.endsWith('/imports') ? [job] : []);
        await studio();
        await fireEvent.click(screen.getByRole('tab', { name: '빌드 기록' }));
        await fireEvent.click(screen.getByRole('button', { name: '작업 #42 상세' }));
        const selected = screen.getByRole('region', { name: '선택한 Dockerfile 작업' });
        await fireEvent.click(within(selected).getByRole('button', { name: '이 작업의 artifact로 VM 생성' }));
        expect(within(selected).getByText(/artifact #1, #3을 사용합니다/)).toBeTruthy();
        const submit = within(selected).getByRole('button', { name: '선택한 작업으로 VM 생성' });
        expect(submit.hasAttribute('disabled')).toBe(true);
        await chooseConsumerFlavor('Flavor ID *', 'Small CPU');
        await fireEvent.input(within(selected).getByLabelText('SSH 공개키 (키페어가 없을 때 필수)'), { target: { value: 'ssh-ed25519 AAAA' } });
        expect(submit.hasAttribute('disabled')).toBe(false);
        mocks.post.mockImplementation(async (path: string) => path.endsWith('/consume') ? { consume_id: 20, server_id: 'vm-20' } : valid);
        await fireEvent.click(submit);
        await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/libraries/consume', {
            import_id: 42, flavor_id: 'flavor-a', ssh_public_key: 'ssh-ed25519 AAAA',
        }, 'token', 'project'));
        expect(screen.getByText(/작업 #42의 artifact로 VM vm-20 생성 완료/)).toBeTruthy();
    });

    it('dispatches consumer specifications without duplicating image or profile inside consumer', async () => {
        await studio();
        await fireEvent.input(screen.getByLabelText('Layer prefix *'), { target: { value: 'sample' } });
        await vi.advanceTimersByTimeAsync(600);
        await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 실행 목표' })).getByRole('button', { name: '인스턴스까지 생성' }));
        expect(screen.getByRole('button', { name: 'Dockerfile 빌드 시작' }).hasAttribute('disabled')).toBe(true);
        await chooseConsumerFlavor('소비 VM Flavor ID *', 'Training GPU');
        await fireEvent.input(screen.getByLabelText('소비 VM 서버 이름 (선택)'), { target: { value: 'studio-vm' } });
        await fireEvent.input(screen.getByLabelText('소비 VM Network ID (선택)'), { target: { value: 'net-1' } });
        await fireEvent.input(screen.getByLabelText('소비 VM SSH 사용자 (선택)'), { target: { value: 'ubuntu' } });
        await fireEvent.input(screen.getByLabelText('소비 VM SSH 공개키 (키페어가 없을 때 필수)'), { target: { value: 'ssh-ed25519 AAAA' } });
        mocks.post.mockClear();
        mocks.post.mockResolvedValue({ id: 50, profile_name: 'sample', status: 'creating_consumer', consume_id: 21, consumer_status: 'creating' });
        await fireEvent.click(screen.getByRole('button', { name: 'Dockerfile 빌드 시작' }));
        const expectedConsumer = { flavor_id: 'flavor-gpu', server_name: 'studio-vm', network_id: 'net-1', ssh_username: 'ubuntu', ssh_public_key: 'ssh-ed25519 AAAA', usage_schedule: defaultSchedule };
        await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/palimpsest/builds/dockerfile', {
            dockerfile: expect.stringContaining('FROM ubuntu:24.04'), layer_prefix: 'sample', consumer: expectedConsumer,
        }, 'token', 'project'));
        await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 입력 방식' })).getByRole('button', { name: 'GitHub 커밋' }));
        await fireEvent.input(screen.getByLabelText('GitHub URL *'), { target: { value: 'https://github.com/example/repo' } });
        await fireEvent.input(screen.getByLabelText('Commit SHA *'), { target: { value: 'c'.repeat(40) } });
        await fireEvent.click(screen.getByRole('button', { name: 'GitHub Dockerfile import 시작' }));
        await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/libraries/imports/dockerfile', {
            github_url: 'https://github.com/example/repo', ref: 'c'.repeat(40), dockerfile_path: 'Dockerfile', layer_prefix: 'sample', consumer: expectedConsumer,
        }, 'token', 'project'));
        for (const [path, body] of mocks.post.mock.calls) {
            if (path !== '/api/v1/palimpsest/builds/dockerfile' && path !== '/api/v1/admin/libraries/imports/dockerfile') continue;
            expect(body.consumer).not.toHaveProperty('image_id');
            expect(body.consumer).not.toHaveProperty('base_image_id');
            expect(body.consumer).not.toHaveProperty('profile_name');
        }
    });

    it('requires an extension reason and propagates only explicit deletion consent for inline consumers', async () => {
        await studio();
        await fireEvent.input(screen.getByLabelText('Layer prefix *'), { target: { value: 'sample' } });
        await vi.advanceTimersByTimeAsync(600);
        await fireEvent.click(within(screen.getByRole('group', { name: 'Dockerfile 실행 목표' })).getByRole('button', { name: '인스턴스까지 생성' }));
        await chooseConsumerFlavor('소비 VM Flavor ID *', 'Large CPU');
        await fireEvent.input(screen.getByLabelText('소비 VM SSH 공개키 (키페어가 없을 때 필수)'), { target: { value: 'ssh-ed25519 AAAA' } });
        const submit = screen.getByRole('button', { name: 'Dockerfile 빌드 시작' });
        const later = new Date(defaultUsageDraft().defaultExpiresAt); later.setUTCDate(later.getUTCDate() + 2);
        await fireEvent.input(document.querySelector('#dockerfile-usage-expires')!, { target: { value: toLocalDateTime(later.toISOString()) } });
        expect(submit.hasAttribute('disabled')).toBe(true);
        await fireEvent.click(submit);
        expect(mocks.post.mock.calls.some(([path]) => path === '/api/v1/palimpsest/builds/dockerfile')).toBe(false);
        await fireEvent.input(document.querySelector('#dockerfile-usage-reason')!, { target: { value: '  Continuing research  ' } });
        await fireEvent.change(document.querySelector('#dockerfile-usage-action')!, { target: { value: 'delete' } });
        const consent = screen.getByRole('checkbox', { name: /연결된 모든 볼륨/ }) as HTMLInputElement;
        expect(consent.checked).toBe(false);
        await fireEvent.click(consent);
        mocks.post.mockImplementation(async (path: string) => path === lintPath ? valid : { id: 60, profile_name: 'sample', status: 'running' });
        await fireEvent.click(submit);
        await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/palimpsest/builds/dockerfile', expect.objectContaining({ consumer: expect.objectContaining({
            usage_schedule: { expires_at: expect.any(String), expiry_action: 'delete', delete_volumes: true, reason: 'Continuing research' },
        }) }), 'token', 'project'));
        expect((document.querySelector('#dockerfile-usage-action') as HTMLSelectElement).value).toBe('shelve');
    });

    it('resets import-consumer consent for changed flavors, execution target and same-tick scope ABA', async () => {
        await studio();
        const targets = within(screen.getByRole('group', { name: 'Dockerfile 실행 목표' }));
        await fireEvent.click(targets.getByRole('button', { name: '인스턴스까지 생성' }));
        await chooseConsumerFlavor('소비 VM Flavor ID *', 'Training GPU');
        await fireEvent.change(document.querySelector('#dockerfile-usage-action')!, { target: { value: 'delete' } });
        await fireEvent.click(screen.getByRole('checkbox', { name: /연결된 모든 볼륨/ }));
        await chooseConsumerFlavor('소비 VM Flavor ID *', 'Large CPU');
        expect((document.querySelector('#dockerfile-usage-action') as HTMLSelectElement).value).toBe('shelve');
        await fireEvent.change(document.querySelector('#dockerfile-usage-action')!, { target: { value: 'delete' } });
        await fireEvent.click(targets.getByRole('button', { name: '레이어만 빌드' }));
        await fireEvent.click(targets.getByRole('button', { name: '인스턴스까지 생성' }));
        expect((document.querySelector('#dockerfile-usage-action') as HTMLSelectElement).value).toBe('shelve');
        auth.update(state => ({ ...state, projectId: 'other-project' }));
        auth.update(state => ({ ...state, projectId: 'project' }));
        await vi.advanceTimersByTimeAsync(0);
        expect(document.querySelector('#dockerfile-usage-action')).toBeNull();
        expect(screen.queryByRole('button', { name: 'Dockerfile 빌드 시작' })).toBeNull();
        await fireEvent.click(screen.getByRole('button', { name: '기존 Dockerfile' }));
        await fireEvent.click(screen.getByRole('button', { name: '편집기로 계속' }));
        await chooseConsumerFlavor('소비 VM Flavor ID *', 'Training GPU');
        expect((document.querySelector('#dockerfile-usage-action') as HTMLSelectElement).value).toBe('shelve');
    });

    it('sends a default schedule for the selected historical artifact and resets after changing jobs', async () => {
        const job = { id: 42, profile_name: 'training', status: 'complete', progress_step: 'complete', progress_pct: 100,
            dockerfile_digest: 'sha256:1234', artifact_ids: [1, 3], build_ids: [5], planned_layers: [], consumer_spec: null, consume_id: null };
        mocks.get.mockImplementation(async (path: string) => path === '/api/v1/flavors' ? consumerFlavors : path.endsWith('/imports') ? [job, { ...job, id: 43 }] : []);
        await studio();
        await fireEvent.click(screen.getByRole('tab', { name: '빌드 기록' }));
        await fireEvent.click(screen.getByRole('button', { name: '작업 #42 상세' }));
        await fireEvent.click(screen.getByRole('button', { name: '이 작업의 artifact로 VM 생성' }));
        await chooseConsumerFlavor('Flavor ID *', 'Training GPU');
        await fireEvent.input(screen.getByLabelText('SSH 공개키 (키페어가 없을 때 필수)'), { target: { value: 'ssh-ed25519 AAAA' } });
        await fireEvent.change(document.querySelector('#history-usage-action')!, { target: { value: 'delete' } });
        await fireEvent.click(screen.getByRole('button', { name: '작업 #43 상세' }));
        await fireEvent.click(screen.getByRole('button', { name: '이 작업의 artifact로 VM 생성' }));
        expect((document.querySelector('#history-usage-action') as HTMLSelectElement).value).toBe('shelve');
        mocks.post.mockImplementation(async (path: string) => path.endsWith('/consume') ? { consume_id: 20, server_id: 'vm-20' } : valid);
        await fireEvent.click(screen.getByRole('button', { name: '선택한 작업으로 VM 생성' }));
        await vi.waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/libraries/consume', {
            import_id: 43, flavor_id: 'flavor-gpu', ssh_public_key: 'ssh-ed25519 AAAA', usage_schedule: defaultSchedule,
        }, 'token', 'project'));
    });
});
