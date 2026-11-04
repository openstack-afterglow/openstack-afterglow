import '../../components/chat/__tests__/lumenPermissionFixture';
import { describe, expect, it, vi } from 'vitest';
import { chatRunExperienceState } from '../chatRunReducer';
import { cancelChatRun, createChatRun, followChatRun, type ChatRunDescriptor } from '../chatStream';
import { getBaseUrl } from '../client';
import { beginExperienceAction, installExperienceCollector } from '$lib/utils/experience';

vi.mock('../lumenAccess', () => ({ requireLumenCapability: vi.fn() }));

const descriptor: ChatRunDescriptor = {
  run_id: 'private-run', conversation_id: 'private-conversation', temp_thread_id: null,
  status: 'queued', run_kind: 'completion',
  events_url: '/api/v1/chat/runs/private-run/events', cancel_url: '/api/v1/chat/runs/private-run/cancel',
};

describe('durable chat experience lifecycle contract', () => {
  it.each(['queued', 'running', 'awaiting_approval', 'awaiting_input', 'waiting_children', 'finalizing'] as const)(
    'does not turn the nonterminal %s state into success', (status) => {
      expect(chatRunExperienceState(status)).toBe('loading');
    },
  );
  it('distinguishes native completion, failure and cancellation', () => {
    expect(chatRunExperienceState('completed')).toBe('ready');
    expect(chatRunExperienceState('failed')).toBe('error');
    expect(chatRunExperienceState('canceled')).toBe('disabled');
  });
  it('uses real authenticated-fetch headers and keeps stream content out of collected wire events', async () => {
    const originalFetch = window.fetch;
    const originalGlobalFetch = globalThis.fetch;
    const requests: { url: string; headers: Headers }[] = [];
    const batches: { events: Record<string, unknown>[] }[] = [];
    const transport = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/experience-contract')) return Response.json({ schema_version: 2, enabled: true, redaction_revision: 1, max_batch_events: 20, max_body_bytes: 32768 });
      if (url.endsWith('/experience-events')) {
        const batch = JSON.parse(String(init?.body));
        batches.push(batch);
        return Response.json({ schema_version: 2, accepted: batch.events.length, duplicates: 0 }, { status: 201 });
      }
      requests.push({ url, headers: new Headers(init?.headers) });
      if (url.includes('/completions')) return Response.json(descriptor, { status: 202 });
      if (url.includes('/cancel')) return new Response(null, { status: 202 });
      return new Response(`id: private-run:1\nevent: run.canceled\ndata: ${JSON.stringify({
        event_id: 'private-run:1', run_id: 'private-run', seq: 1, type: 'run.canceled',
        created_at: '2026-11-04T00:00:00Z', payload: { status: 'canceled', message_id: null, error_code: 'canceled', safe_message: 'private-result' },
      })}\n\n`, { status: 200 });
    });
    window.fetch = transport;
    globalThis.fetch = transport;
    const collector = installExperienceCollector({
      getOwner: () => ({ token: 'private-token', sessionId: 'session-a', userId: 'user-a', domainId: 'domain-a', projectId: 'project-a' }),
      getRoute: () => '/dashboard/chat', getBaseUrl,
      isEnabled: () => true, isSuppressed: () => false,
      subscribeOwner: () => () => {},
    });
    try {
      const experience = beginExperienceAction('lumen', 'submit', 'shared.stream')!;
      const created = await createChatRun('/api/v1/chat/conversations/private-conversation/completions', { parts: [{ type: 'text', text: 'private-prompt' }] }, { experience });
      expect(created.status).toBe('queued');
      const events = [];
      for await (const event of followChatRun(created, { experience })) events.push(event.type);
      expect(events).toEqual(['run.canceled']);
      await cancelChatRun(created, { experience });
      expect(created.status).toBe('queued');
      await collector.flush();
      expect(requests).toHaveLength(3);
      expect(requests.every(({ headers }) => headers.get('X-Afterglow-Experience-Action') === experience.actionId)).toBe(true);
      expect(new Set(requests.map(({ headers }) => headers.get('X-Afterglow-Experience-Span'))).size).toBe(3);
      const rows = batches.flatMap(batch => batch.events);
      expect(rows.filter(row => row.event_type === 'result.received')).toHaveLength(3);
      expect(rows.some(row => row.event_type === 'result.applied')).toBe(false);
      expect(JSON.stringify(batches)).not.toMatch(/private-prompt|private-result|private-run|private-conversation|private-token/);
    } finally {
      collector.destroy();
      window.fetch = originalFetch;
      globalThis.fetch = originalGlobalFetch;
    }
  });
});
