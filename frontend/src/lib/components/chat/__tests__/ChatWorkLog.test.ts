import { fireEvent, render } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
import ExecutionTimeline from '../ExecutionTimeline.svelte';
import ChatWindow from '../ChatWindow.svelte';
import type { RunActivityItem } from '$lib/api/chatRunReducer';

const startedAt = '2026-11-17T00:00:00Z';
const stage: RunActivityItem = { id: 'stage', kind: 'stage', seq: 2, createdAt: '2026-11-17T00:00:01Z', stage: 'model_request', toolName: null };
const reason: RunActivityItem = { id: 'reason', kind: 'reasoning', seq: 3, createdAt: '2026-11-17T00:00:02Z', text: 'User-visible planning summary', active: false };
const tool: RunActivityItem = { id: 'tool', kind: 'tool', seq: 4, createdAt: '2026-11-17T00:00:03Z', callId: 'call', name: 'web_search', source: 'builtin', category: 'Web', arguments: {}, status: 'failed', content: [{ type: 'text', text: 'Search unavailable' }], errorCode: 'unavailable', durationMs: 1000 };
const terminal: RunActivityItem = { id: 'end', kind: 'terminal', seq: 5, createdAt: '2026-11-17T00:00:12Z', status: 'completed', message: null, errorCode: null };
const history = [stage, reason, tool, terminal];
const callbacks = { onCopy: vi.fn(), onRegenerate: vi.fn(), onRetry: vi.fn(), onFork: vi.fn(), onSwitchVersion: vi.fn() };
afterEach(() => vi.useRealTimers());

it('shows quiet preparation before any step or answer arrives', () => {
    const view = render(ChatWindow, { activePath: [{ id: 'draft', role: 'assistant', conversation_id: 'c', parent_id: null, content: '', created_at: null, streaming: true }], models: [], ...callbacks });
    expect(view.getByText('응답을 준비하는 중…')).toBeTruthy();
    expect(view.container.querySelector('.execution-timeline')).toBeNull();
});

it('counts live time from actual start and collapses once when terminal arrives', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
    vi.setSystemTime(new Date('2026-11-17T00:00:08Z'));
    const view = render(ExecutionTimeline, { items: [stage], startedAt, active: true, animate: false });
    expect(view.getByText('8초 동안 작업 중')).toBeTruthy();
    await vi.advanceTimersByTimeAsync(1000);
    expect(view.getByText('9초 동안 작업 중')).toBeTruthy();
    await view.rerender({ items: history, active: false });
    const details = view.container.querySelector('.execution-timeline') as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(view.getByText('12초 동안 작업함')).toBeTruthy();
    await fireEvent.click(view.getByText('12초 동안 작업함'));
    expect(details.open).toBe(true);
    await vi.advanceTimersByTimeAsync(10000);
    expect(view.getByText('12초 동안 작업함')).toBeTruthy();
    expect(details.open).toBe(true);
});

it('restores complete history above answer after remount and keeps failed tools and reasoning inspectable', async () => {
    const props = { activePath: [{ id: 'answer', role: 'assistant' as const, conversation_id: 'c', parent_id: null, content: 'Final answer', created_at: null, execution: { run_id: 'run', started_at: startedAt, activity: history } }], models: [], ...callbacks };
    let view = render(ChatWindow, props);
    view.unmount();
    view = render(ChatWindow, props);
    const summary = view.getByText('12초 동안 작업함');
    expect(view.container.querySelector('.execution-timeline')?.compareDocumentPosition(view.getByText('Final answer'))).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    await fireEvent.click(summary);
    await fireEvent.click(view.getByText('Web'));
    expect(view.getByText('실패')).toBeTruthy();
    await fireEvent.click(view.container.querySelector('.tool-head')!);
    expect(view.getByText('Search unavailable')).toBeTruthy();
    await fireEvent.click(view.getByText('추론 과정'));
    expect(view.getByText('User-visible planning summary')).toBeTruthy();
    expect(view.container.querySelector('.motion-enter, .motion-pop')).toBeNull();
    await fireEvent.click(summary);
    expect(summary.closest('summary')?.getAttribute('aria-expanded')).toBe('false');
});

it('renders permission inside live flow and sends only explicit existing decisions', async () => {
    const onApprovalDecision = vi.fn();
    const approval: RunActivityItem = { id: 'approval', kind: 'approval', seq: 3, createdAt: '2026-11-17T00:00:02Z', callId: 'call', name: 'afterglow_vm_create', effect: 'external_mutation', arguments: { name: 'sample' }, preview: [{ type: 'text', text: 'Create sample VM?' }], expiresAt: '2099-11-17T01:00:00Z', destination: null, decision: null, decidedAt: null };
    const pendingApprovals = [{ callId: 'call', name: 'afterglow_vm_create', effect: 'external_mutation' as const, argumentKeys: ['name'], preview: approval.preview, expiresAt: '2099-11-17T01:00:00Z' }];
    const view = render(ExecutionTimeline, { items: [stage, approval], startedAt, active: true, pendingApprovals, onApprovalDecision });
    expect(view.getByText('권한')).toBeTruthy();
    expect(view.getByText('Create sample VM?').closest('ol')).toBeTruthy();
    expect(onApprovalDecision).not.toHaveBeenCalled();
    await fireEvent.click(view.getByRole('button', { name: '이번만 허용하기' }));
    expect(onApprovalDecision).toHaveBeenCalledWith('call', 'approve');
    await view.rerender({ approvalBusy: true });
    expect(view.getByRole('button', { name: '거부' }).hasAttribute('disabled')).toBe(true);
    await view.rerender({ approvalBusy: false });
    await fireEvent.click(view.getByRole('button', { name: '거부' }));
    expect(onApprovalDecision).toHaveBeenLastCalledWith('call', 'deny');
});

it('does not fabricate elapsed duration for legacy or incomplete stored history', () => {
    const view = render(ExecutionTimeline, { items: [stage], active: false, animate: false });
    expect(view.container.querySelector('.execution-timeline > summary')?.textContent).toContain('실행 기록');
    expect(view.container.querySelector('.motion-enter, .motion-pop')).toBeNull();
});

it('keeps live work inspectable without entrance motion under reduced motion', async () => {
    const previous = window.matchMedia;
    window.matchMedia = vi.fn().mockReturnValue({ matches: true });
    try {
        const view = render(ExecutionTimeline, { items: [], active: true, animate: true });
        await view.rerender({ items: [stage, reason, tool], startedAt });
        expect(view.container.querySelector('.execution-timeline[open]')).toBeTruthy();
        expect(view.container.querySelector('.motion-enter, .motion-pop')).toBeNull();
        expect(view.getByText('실패')).toBeTruthy();
    } finally {
        window.matchMedia = previous;
    }
});

it('names unavailable consumed history without dropping the final answer or fabricating a complete log', () => {
    const view = render(ChatWindow, {
        activePath: [{
            id: 'answer', role: 'assistant', conversation_id: 'c', parent_id: null, content: 'Valid final body',
            created_at: null, execution: {
                run_id: 'run', started_at: null, activity: null,
                activity_status: 'unavailable', activity_error_code: 'history_activity_invalid'
            }
        }], models: [], ...callbacks
    });
    expect(view.getByText('Valid final body')).toBeTruthy();
    expect(view.getByRole('status').textContent).toContain('작업 내역을 불러올 수 없습니다.');
    expect(view.container.querySelector('.execution-timeline')).toBeNull();
});

it('uses exact pending run and call ownership after a positioned follower stops', async () => {
    const onApprovalDecision = vi.fn();
    const approval: RunActivityItem = { id: 'approval', kind: 'approval', seq: 2, createdAt: startedAt, callId: 'same-call', name: 'inspect', effect: 'read', arguments: {}, preview: [{ type: 'text', text: 'Owned pending request' }], expiresAt: '2099-11-17T01:00:00Z', destination: null, decision: null, decidedAt: null };
    const pendingApprovals = [
        { runId: 'owned-run', callId: 'same-call', name: 'inspect', effect: 'read' as const, argumentKeys: [], preview: approval.preview, expiresAt: approval.expiresAt! },
        { runId: 'foreign-run', callId: 'same-call', name: 'inspect', effect: 'read' as const, argumentKeys: [], preview: [{ type: 'text' as const, text: 'Other run request' }], expiresAt: approval.expiresAt! }
    ];
    const view = render(ChatWindow, {
        activePath: [{ id: 'draft', role: 'assistant', conversation_id: 'c', parent_id: null, content: '', created_at: null, streaming: false, execution: { run_id: 'owned-run', activity: [approval] } }],
        pendingApprovals, onApprovalDecision, models: [], ...callbacks
    });
    expect(view.getByText('Owned pending request')).toBeTruthy();
    expect(view.queryByText('Other run request')).toBeNull();
    expect(view.container.querySelector('.execution-timeline[open]')).toBeTruthy();
    await fireEvent.click(view.getByRole('button', { name: '거부' }));
    expect(onApprovalDecision).toHaveBeenCalledWith('owned-run', 'same-call', 'deny');
    await view.rerender({ pendingApprovals: [] });
    expect(view.queryByRole('button', { name: '이번만 허용하기' })).toBeNull();
});

it('never reactivates a decided approval from stale pending props', () => {
    const approval: RunActivityItem = { id: 'approval', kind: 'approval', seq: 2, createdAt: startedAt, callId: 'call', name: 'inspect', effect: 'read', arguments: {}, preview: [], expiresAt: '2099-11-17T01:00:00Z', destination: null, decision: 'deny', decidedAt: startedAt };
    const view = render(ExecutionTimeline, {
        items: [approval], active: false,
        pendingApprovals: [{ callId: 'call', name: 'inspect', effect: 'read', argumentKeys: [], preview: [], expiresAt: '2099-11-17T01:00:00Z' }],
        onApprovalDecision: vi.fn()
    });
    expect(view.queryByRole('button', { name: '이번만 허용하기' })).toBeNull();
    expect(view.queryByRole('button', { name: '거부' })).toBeNull();
});
