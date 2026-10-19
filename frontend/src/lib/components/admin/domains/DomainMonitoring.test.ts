import { cleanup, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { ApiError } from '$lib/api/errors';
import type { DomainMonitoring } from '$lib/api/domains';
import DomainMonitoringComponent from './DomainMonitoring.svelte';
const mocks = vi.hoisted(() => ({ monitoring: vi.fn() }));
vi.mock('$lib/api/domains', () => ({ domainsApi: mocks }));
const snapshot: DomainMonitoring = {
  domain: { id: 'tenant-a', name: 'Research', enabled: true }, directory: { users: 0, projects: 0 },
  resources: [
    { service: 'nova', metric: 'instances', kind: 'count', value: 0, unit: 'count', status: 'ready' },
    { service: 'swift', metric: 'buckets', kind: 'count', value: null, unit: 'count', status: 'unavailable', error: 'domain_aggregate_unsupported' },
  ],
  requests: { state: 'partial', window: '24h', total: null, errors: null, services: [], timeline: null },
  logins: { state: 'unavailable', successes: null, recorded_failures: null, failure_history: 'not_collected', timeline: null },
  sessions: { state: 'partial', valid_count: null, observed_recent_count: null, unattributed_count: null, online_count: null },
  activity: { state: 'unavailable', recent_users: null, events: null, last_seen: null, hour_distribution: null },
  coverage: { window: '24h', observed_at: '2026-10-15T08:00:00Z', partial: true, notes: [] },
};
beforeEach(() => { vi.resetAllMocks(); initLocale('en'); auth.update(state => ({ ...state, token: 'system-token', projectId: 'operator-project', isSystemAdmin: true })); });
afterEach(() => { cleanup(); initLocale('ko'); });

describe('whole-domain observations', () => {
  it('keeps measured zero distinct from unavailable resources and online presence', async () => {
    mocks.monitoring.mockResolvedValue(snapshot);
    render(DomainMonitoringComponent, { domainId: 'tenant-a', domainName: 'Research' });
    const metric = await screen.findByText('instances');
    expect(within(metric.closest('tr')!).getByText('0 count')).toBeTruthy();
    const unknown = screen.getByText('buckets');
    expect(within(unknown.closest('tr')!).queryByText('0 count')).toBeNull();
    expect(within(unknown.closest('tr')!).getAllByText('Unavailable')).toHaveLength(2);
    const online = screen.getByText('Currently online users');
    expect(within(online.closest('tr')!).queryByText('0')).toBeNull();
    expect(screen.getByText('Valid sessions are not online users. Recent activity represents observed requests only.')).toBeTruthy();
  });

  it('shows native denial without a successful empty dashboard', async () => {
    mocks.monitoring.mockRejectedValue(new ApiError(403, 'domain_monitoring_native_denied'));
    render(DomainMonitoringComponent, { domainId: 'tenant-a', domainName: 'Research' });
    await screen.findByText('domain_monitoring_native_denied');
    expect(screen.queryByText('Whole-domain summary')).toBeNull();
  });

  it('ignores a pending foreign-domain snapshot', async () => {
    const { promise, resolve } = Promise.withResolvers<DomainMonitoring>();
    mocks.monitoring.mockReturnValueOnce(promise);
    mocks.monitoring.mockResolvedValue({ ...snapshot, domain: { ...snapshot.domain, id: 'tenant-b', name: 'Second tenant' }, resources: [] });
    const view = render(DomainMonitoringComponent, { domainId: 'tenant-a', domainName: 'Research' });
    await tick();
    await view.rerender({ domainId: 'tenant-b', domainName: 'Second tenant' });
    resolve(snapshot);
    await tick();
    expect(screen.queryByText('instances')).toBeNull();
  });
});
