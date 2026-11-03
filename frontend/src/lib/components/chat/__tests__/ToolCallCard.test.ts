import { fireEvent, render } from '@testing-library/svelte';
import { expect, it } from 'vitest';
import ToolCallCard from '../ToolCallCard.svelte';

it('shows labeled running work and pops completion only after a live run', async () => {
	const item = { id: 'call-1', name: 'managed_web_search', args: null, result: null, running: true };
	const view = render(ToolCallCard, { item });
	expect(view.getByText('실행 중…')).toBeTruthy();
	await view.rerender({ item: { ...item, running: false, status: 'completed' } });
	expect(view.getByText('완료')).toBeTruthy();
	expect(view.container.querySelector('.motion-pop')).toBeTruthy();
	view.unmount();
	const stored = render(ToolCallCard, { item: { ...item, running: false, status: 'completed' } });
	expect(stored.container.querySelector('.motion-pop')).toBeNull();
});

it('shows a visible failure label and X instead of a completion check', () => {
	const view = render(ToolCallCard, { item: { id: 'call-1', name: 'managed_web_search', args: null, result: null, running: false, status: 'failed' } });
	expect(view.getByText('실패')).toBeTruthy();
	expect(view.queryByText('완료')).toBeNull();
	expect(view.container.querySelector('.motion-pop')).toBeNull();
});

it('shows factual live progress immediately and retains its ordered detail after completion', async () => {
	const item = { id: 'call-1', name: 'managed_web_search', running: true, progress: ['Read 2 results', 'Fetched selected page'] };
	const view = render(ToolCallCard, { item });
	expect(view.getByRole('status').textContent).toContain('Fetched selected page');
	expect(view.queryByText('Read 2 results')).toBeNull();
	await view.rerender({ item: { ...item, running: false, status: 'completed' } });
	await fireEvent.click(view.container.querySelector('.tool-head')!);
	expect(view.getByText('Read 2 results')).toBeTruthy();
	expect(view.getAllByText('Fetched selected page')).toHaveLength(2);
	expect(view.queryByText('추론 과정')).toBeNull();
});
