import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it } from 'vitest';
import { tick } from 'svelte';
import { parseChatRunEvent, ChatContractError } from '$lib/api/chatContracts';
import { createRunViewState, reduceRunEvent, type RunActivityItem } from '$lib/api/chatRunReducer';
import { initLocale } from '$lib/i18n/runtime.svelte';
import ExecutionTimeline from '../ExecutionTimeline.svelte';

const at = '2026-11-03T00:00:00Z';
const created = { child_run_id: 'child-1', call_id: 'delegate-1', wait_group_id: 'group-1', agent_id: 42, access: 'read', ordinal: 0, status: 'waiting_resource' };
const artifact = { type: 'file', asset_id: 'e83a2892-41f0-4ca2-a453-4e23118f32ba', mime_type: 'text/csv', name: 'observations.csv', size_bytes: 128 };
function event(seq: number, type: string, payload: object) {
	return parseChatRunEvent({ event_id: `run-1:${seq}`, run_id: 'run-1', seq, type, created_at: at, payload });
}
beforeEach(() => initLocale('ko'));

describe('canonical child events through reducer and timeline', () => {
	it('shows only the factual request until terminal, not an invented current resource/running phase', async () => {
		const state = reduceRunEvent(createRunViewState('run-1'), event(1, 'child.created', created));
		expect(state.children['child-1']).toMatchObject({ status: 'requested', initialStatus: 'waiting_resource', callId: 'delegate-1', waitGroupId: 'group-1' });
		const view = render(ExecutionTimeline, { items: state.activity, active: true });
		await tick();
		expect(screen.getByText('하위 작업 요청됨')).toBeTruthy();
		expect(view.container.querySelector('.loading-state')).toBeNull();
		expect(view.container.querySelector('li.live')).toBeNull();
		await fireEvent.click(screen.getByText('하위 작업 요청 정보'));
		expect(screen.getByText('요청 시점 상태')).toBeTruthy();
		expect(screen.getByText('리소스 대기')).toBeTruthy();
		expect(screen.getByText('child-1')).toBeTruthy();
		expect(screen.getByText('delegate-1')).toBeTruthy();
		expect(screen.getByText('group-1')).toBeTruthy();
	});

	it.each([
		['completed', '완료', null], ['failed', '실패', 'child_failed'], ['canceled', '취소됨', 'child_canceled']
	] as const)('renders terminal %s summary and artifact metadata, including reloaded history', async (status, label, error_code) => {
		let state = reduceRunEvent(createRunViewState('run-1'), event(1, 'child.created', created));
		const view = render(ExecutionTimeline, { items: state.activity, active: true });
		state = reduceRunEvent(state, event(2, 'child.completed', { child_run_id: 'child-1', call_id: 'delegate-1', wait_group_id: 'group-1', status, error_code, summary: 'Observed child outcome, not parent reasoning.', artifacts: [artifact] }));
		expect(state.activity).toHaveLength(1);
		expect(state.activity[0]).toMatchObject({ seq: 1, createdAt: at, kind: 'child', status, agentId: 42, access: 'read', ordinal: 0 });
		await view.rerender({ items: state.activity, active: false });
		expect(screen.getByText(label)).toBeTruthy();
		expect(screen.queryByText('하위 작업 요청됨')).toBeNull();
		expect(screen.getByText('Observed child outcome, not parent reasoning.')).toBeTruthy();
		const link = screen.getByRole('link', { name: /observations.csv/ });
		expect(link.getAttribute('href')).toBe(`/lumen/sources/assets/${artifact.asset_id}`);
		expect(link.textContent).toContain('text/csv');
		expect(link.textContent).toContain('128 B');
		if (error_code) expect(screen.getByText(error_code)).toBeTruthy();
		view.unmount();
		const history: RunActivityItem[] = JSON.parse(JSON.stringify(state.activity));
		const restored = render(ExecutionTimeline, { items: history, active: false });
		expect(screen.getByText(label)).toBeTruthy();
		expect(screen.getByText('Observed child outcome, not parent reasoning.')).toBeTruthy();
		expect(restored.container.querySelector('.loading-state, .motion-pop, li.live')).toBeNull();
	});

	it('keeps sibling children separate and rejects a terminal result for another call/wait group', () => {
		let state = reduceRunEvent(createRunViewState('run-1'), event(1, 'child.created', created));
		state = reduceRunEvent(state, event(2, 'child.created', { ...created, child_run_id: 'child-2', ordinal: 1, status: 'queued' }));
		state = reduceRunEvent(state, event(3, 'child.completed', { child_run_id: 'child-2', call_id: 'delegate-1', wait_group_id: 'group-1', status: 'completed', summary: 'Second child' }));
		expect(state.children['child-1'].status).toBe('requested');
		expect(state.children['child-2'].status).toBe('completed');
		expect(state.activity.map((item) => item.id)).toEqual(['child:child-1', 'child:child-2']);
		expect(() => reduceRunEvent(state, event(4, 'child.completed', { child_run_id: 'child-1', call_id: 'foreign-call', wait_group_id: 'group-1', status: 'failed' }))).toThrow('identity conflict');
		expect(() => reduceRunEvent(state, event(4, 'child.completed', { child_run_id: 'child-1', call_id: 'delegate-1', wait_group_id: 'foreign-group', status: 'failed' }))).toThrow('identity conflict');
	});

	it('supports terminal-only retained history without inventing missing admission metadata', () => {
		const state = reduceRunEvent(createRunViewState('run-1'), event(1, 'child.completed', { child_run_id: 'child-1', call_id: 'delegate-1', wait_group_id: 'group-1', status: 'canceled' }));
		expect(state.children['child-1']).toMatchObject({ agentId: null, access: null, ordinal: null, initialStatus: null, status: 'canceled', summary: '', artifacts: [] });
	});
});

describe('strict public child event contract', () => {
	it('rejects private child sources, unknown keys/kinds and non-file artifact payloads', () => {
		expect(() => event(1, 'child.created', { ...created, current_phase: 'running' })).toThrow(ChatContractError);
		expect(() => event(1, 'child.completed', { child_run_id: 'child-1', call_id: 'delegate-1', wait_group_id: 'group-1', status: 'completed', sources: [] })).toThrow(ChatContractError);
		expect(() => event(1, 'child.completed', { child_run_id: 'child-1', call_id: 'delegate-1', wait_group_id: 'group-1', status: 'completed', artifacts: [{ type: 'text', text: 'not a file' }] })).toThrow(ChatContractError);
		expect(() => event(1, 'child.future', created)).toThrow(ChatContractError);
	});
	it('enforces backend enum, identity and summary/artifact bounds', () => {
		expect(() => event(1, 'child.created', { ...created, agent_id: 0 })).toThrow(ChatContractError);
		expect(() => event(1, 'child.created', { ...created, child_run_id: 'x'.repeat(37) })).toThrow(ChatContractError);
		expect(() => event(1, 'child.created', { ...created, status: 'running' })).toThrow(ChatContractError);
		const terminal = { child_run_id: 'child-1', call_id: 'delegate-1', wait_group_id: 'group-1', status: 'completed' };
		expect(() => event(1, 'child.completed', { ...terminal, summary: 'x'.repeat(8193) })).toThrow(ChatContractError);
		expect(() => event(1, 'child.completed', { ...terminal, artifacts: Array.from({ length: 21 }, () => artifact) })).toThrow(ChatContractError);
		expect(event(1, 'child.completed', { ...terminal, summary: '😀'.repeat(8192) })).toMatchObject({ type: 'child.completed' });
	});
});
