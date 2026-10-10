import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/svelte';
import DocCodeBlock from './DocCodeBlock.svelte';

const command = { label: 'kubeconfig', code: 'kubectl config current-context' };

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
});

describe('copy feedback ownership', () => {
	it('does not announce a pending old-language copy after switching away and back', async () => {
		let finish: () => void = () => { throw new Error('Clipboard operation has not started'); };
		const pending = new Promise<void>((resolve) => { finish = resolve; });
		vi.stubGlobal('navigator', { clipboard: { writeText: () => pending } });
		const view = render(DocCodeBlock, { command, locale: 'en' });
		await fireEvent.click(view.getByRole('button'));
		await view.rerender({ command, locale: 'ja' });
		await view.rerender({ command, locale: 'en' });
		finish();
		await pending;
		await Promise.resolve();
		expect(view.queryByRole('status')).toBeNull();
	});

	it('does not announce a prior command when its clipboard operation finishes', async () => {
		let finish: () => void = () => { throw new Error('Clipboard operation has not started'); };
		const pending = new Promise<void>((resolve) => { finish = resolve; });
		vi.stubGlobal('navigator', { clipboard: { writeText: () => pending } });
		const view = render(DocCodeBlock, { command, locale: 'en' });
		await fireEvent.click(view.getByRole('button'));
		await view.rerender({ command: { label: 'nodes', code: 'kubectl get nodes' }, locale: 'en' });
		finish();
		await pending;
		await Promise.resolve();
		expect(view.queryByRole('status')).toBeNull();
	});
});
