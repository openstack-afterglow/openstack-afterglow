import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import DockerfileLintPanel, { type DockerfileLintResponse } from '../DockerfileLintPanel.svelte';

const image = { id: '12345678-abcdef', name: 'ubuntu:24.04-server', ubuntu_base: 'ubuntu-24.04', min_disk: 10, visibility: 'public' };
const valid: DockerfileLintResponse = {
	valid: true, diagnostics: [], warnings: [],
	from: { line: 1, ref: 'ubuntu:24.04-server', kind: 'glance_name', image, parent: null, completions: [], error: null, note: null },
	layers: { new: 3, inherited: 0, total: 3, limit: 25, by_instruction: { RUN: 1, ENV: 1, WORKDIR: 1 } },
};
const ambiguous: DockerfileLintResponse = {
	...valid, valid: false,
	from: {
		...valid.from, image: null, kind: 'ubuntu_tag', ref: 'ubuntu:24.04',
		error: 'Ubuntu 24.04 이미지가 2개 있습니다 — FROM에 아래 이미지 이름 또는 UUID를 지정하세요',
		completions: [{ ref: 'ubuntu:24.04-server', id: image.id, name: image.name, ubuntu_base: image.ubuntu_base, created_at: '2026-09-26T10:00:00Z' }],
	},
};
const clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
afterEach(() => {
	cleanup();
	if (clipboardDescriptor) Object.defineProperty(navigator, 'clipboard', clipboardDescriptor);
	else Reflect.deleteProperty(navigator, 'clipboard');
});

describe('Dockerfile lint panel', () => {
	it('displays all syntax diagnostics with source line numbers', () => {
		render(DockerfileLintPanel, { props: {
			lint: { ...valid, valid: false, diagnostics: [{ line: 2, message: 'ARG는 지원하지 않습니다' }, { line: 4, message: 'COPY에는 빌드 컨텍스트가 필요합니다' }] },
			loading: false, requestError: '',
		} });
		const panel = screen.getByRole('region', { name: 'Dockerfile 검사' });
		expect(within(panel).getByText('오류 2개')).toBeTruthy();
		expect(within(panel).getByText('L2')).toBeTruthy();
		expect(within(panel).getByText('L4')).toBeTruthy();
		expect(within(panel).getByText(/ARG는 지원하지 않습니다/)).toBeTruthy();
		expect(within(panel).getByText(/COPY에는 빌드 컨텍스트가 필요합니다/)).toBeTruthy();
	});

	it('shows the resolved Glance image and layer instruction breakdown', () => {
		render(DockerfileLintPanel, { props: { lint: valid, loading: false, requestError: '' } });
		const panel = screen.getByRole('region', { name: 'Dockerfile 검사' });
		expect(within(panel).getByText('문법 OK · 레이어 3개')).toBeTruthy();
		expect(within(panel).getByText(/Glance ubuntu:24.04-server.*12345678…/)).toBeTruthy();
		expect(within(panel).getByText(/RUN 1 · ENV 1 · WORKDIR 1/)).toBeTruthy();
	});

	it('lists ambiguous FROM completions as selectable text and copies the full instruction', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
		render(DockerfileLintPanel, { props: { lint: ambiguous, loading: false, requestError: '' } });
		const panel = screen.getByRole('region', { name: 'Dockerfile 검사' });
		expect(within(panel).getByText('FROM 미해결')).toBeTruthy();
		expect(within(panel).getByText('FROM ubuntu:24.04-server').tagName).toBe('CODE');
		await fireEvent.click(within(panel).getByRole('button', { name: '복사' }));
		expect(writeText).toHaveBeenCalledWith('FROM ubuntu:24.04-server');
		expect(within(panel).getByRole('button', { name: '복사됨' })).toBeTruthy();
	});

	it('offers unknown-name completions with a copyable UUID reference', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
		render(DockerfileLintPanel, { props: {
			lint: {
				...ambiguous,
				from: {
					...ambiguous.from, kind: null, ref: 'custom', error: "Glance에서 active Ubuntu 이미지 'custom'를 찾을 수 없습니다",
					completions: [{ ref: '12345678-abcdef', id: image.id, name: 'custom image', ubuntu_base: 'ubuntu-24.04', created_at: null }],
				},
			}, loading: false, requestError: '',
		} });
		expect(screen.getByText('FROM 12345678-abcdef')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '복사' }));
		expect(writeText).toHaveBeenCalledWith('FROM 12345678-abcdef');
	});

	it('explains clipboard failure without hiding the copyable completion', async () => {
		Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } });
		render(DockerfileLintPanel, { props: { lint: ambiguous, loading: false, requestError: '' } });
		await fireEvent.click(screen.getByRole('button', { name: '복사' }));
		expect(screen.getByText(/복사하지 못했습니다/)).toBeTruthy();
		expect(screen.getByText('FROM ubuntu:24.04-server')).toBeTruthy();
	});

	it('shows resolved parent depth and the over-limit warning', () => {
		render(DockerfileLintPanel, { props: {
			lint: {
				...valid, warnings: [{ line: null, message: '예상 체인 길이 26개가 로컬 KVM 레이어 상한 25개를 넘습니다' }],
				from: { ...valid.from, kind: 'palimpsest', ref: 'abc', image: null, parent: { id: 7, name: 'python', blob_digest: null, ubuntu_base: 'ubuntu-24.04', base_image_name: null, chain_depth: 24 } },
				layers: { new: 2, inherited: 24, total: 26, limit: 25, by_instruction: { RUN: 2 } },
			}, loading: false, requestError: '',
		} });
		expect(screen.getByText(/FROM 부모 레이어 python #7.*체인 24개/)).toBeTruthy();
		expect(screen.getByText(/총 26개 \/ 상한 25/)).toBeTruthy();
		expect(screen.getByText(/예상 체인 길이 26개가 로컬 KVM/)).toBeTruthy();
	});
});
