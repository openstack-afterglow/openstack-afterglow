import { afterEach, expect, it, vi } from 'vitest';
import { parseChatRunEvent } from '$lib/api/chatContracts';
import { mockChatWorkLog, mockChatWorkLogResponse } from './chatWorkLog';

afterEach(() => vi.useRealTimers());
it('uses actual SSE framing, blocks on permission and retains the complete journal', async () => {
    vi.useFakeTimers();
    const path = '/api/v1/chat/conversations/tutorial-work-log/completions';
    const accepted = mockChatWorkLogResponse(path, { method: 'POST' })!;
    expect(accepted.status).toBe(202);
    const descriptor = await accepted.json();
    const stream = mockChatWorkLogResponse(descriptor.events_url, {})!;
    const reader = stream.body!.getReader();
    await vi.advanceTimersByTimeAsync(8000);
    let frames = '';
    for (let index = 0; index < 5; index++) frames += new TextDecoder().decode((await reader.read()).value);
    const events = frames.split('\n\n').filter(Boolean).map((frame) => parseChatRunEvent(JSON.parse(frame.split('\ndata: ')[1])));
    expect(events.at(-1)?.type).toBe('tool.approval_required');
    expect(events.some((event) => event.type === 'tool.call.started')).toBe(false);
    mockChatWorkLog('POST', `/api/v1/chat/runs/${descriptor.run_id}/approvals/permission`, new URLSearchParams(), { decision: 'deny' });
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        frames += new TextDecoder().decode(value);
    }
    expect(frames).toContain('run.completed');
    expect(frames).toContain('tutorial_unavailable');
    const page = mockChatWorkLog('GET', '/api/v1/chat/conversations/tutorial-work-log/messages', new URLSearchParams(), undefined);
    expect(JSON.stringify(page)).toContain('"decision":"deny"');
    expect(JSON.stringify(page)).not.toContain('"kind":"started"');
    expect(page).toMatchObject({ messages: [expect.anything(), {
        execution: { started_at: events[0].created_at, activity: expect.arrayContaining([
            expect.objectContaining({ kind: 'stage' }), expect.objectContaining({ kind: 'terminal' })
        ]) }
    }] });
    expect(JSON.stringify(page)).toContain('"kind":"terminal"');
});
