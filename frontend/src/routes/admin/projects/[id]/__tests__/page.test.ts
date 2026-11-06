import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import { t as tc } from '$lib/i18n/ns/common';
import { t as ti } from '$lib/i18n/ns/admin-identity';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock('$app/stores', () => ({ page: writable({ params: { id: 'project-1' }, data: {} }) }));
vi.mock('$lib/api/client', () => ({
  api: { get: mockGet },
  ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } },
}));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'admin-project' }) }));
import Page from '$lib/components/admin/projects/AdminProjectDetailPage.svelte';
import { auth } from '$lib/stores/auth';
import { ApiError } from '$lib/api/client';

const project = { id: 'project-1', name: 'Project One', description: 'Primary content', enabled: true, domain_id: 'domain-a', created_at: null };

beforeEach(() => { mockGet.mockReset(); auth.update(state => ({ ...state, token: 'token', projectId: 'admin-project' })); });
describe('project detail loading boundaries', () => {
  it('verifies the exact project domain before requesting members, while members can remain independently pending', async () => {
    const primary = Promise.withResolvers<typeof project>();
    const members = Promise.withResolvers<unknown[]>();
    mockGet.mockImplementation((path: string) => path.includes('/members?') ? members.promise : primary.promise);
    render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    await waitFor(() => expect(mockGet).toHaveBeenCalledOnce());
    expect(mockGet).toHaveBeenCalledWith('/api/v1/admin/projects/project-1?domain_id=domain-a', 'token', 'admin-project');
    primary.resolve(project);
    expect((await screen.findAllByText('Project One')).length).toBeGreaterThan(0);
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
    expect(mockGet.mock.calls[1][0]).toBe('/api/v1/admin/projects/project-1/members?domain_id=domain-a');
    expect(screen.getByRole('link', { name: '← 목록' }).getAttribute('href')).toBe('/admin/projects?domain_id=domain-a');
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    expect(screen.getByRole('status').textContent).toContain('멤버를 불러오는 중...');
    members.reject(new Error('members unavailable'));
    expect(await screen.findByText('멤버 조회 실패')).toBeTruthy();
    expect(screen.queryByText('멤버를 불러오는 중...')).toBeNull();
  });

  it.each([null, 'domain-b'])('rejects absent or foreign domain %s before related lookups', async (domain_id) => {
    mockGet.mockResolvedValue({ ...project, domain_id });
    render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    expect(await screen.findByText('프로젝트 조회 실패')).toBeTruthy();
    expect(screen.queryByText('Project One')).toBeNull();
    expect(mockGet).toHaveBeenCalledOnce();
  });

  it('discards a late old-domain project after changing selection', async () => {
    const first = Promise.withResolvers<typeof project>();
    const second = Promise.withResolvers<typeof project>();
    mockGet.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockResolvedValue([]);
    const view = render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    await waitFor(() => expect(mockGet).toHaveBeenCalledOnce());
    await view.rerender({ domainId: 'domain-b', domainName: 'Domain B' });
    first.resolve(project);
    await tick();
    expect(screen.queryByText('Project One')).toBeNull();
    second.resolve({ ...project, domain_id: 'domain-b', name: 'Domain B project' });
    expect((await screen.findAllByText('Domain B project')).length).toBeGreaterThan(0);
  });

  it('never starts related requests after unmount', async () => {
    const pending = Promise.withResolvers<typeof project>();
    mockGet.mockReturnValueOnce(pending.promise);
    const view = render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    await waitFor(() => expect(mockGet).toHaveBeenCalledOnce());
    view.unmount();
    pending.resolve(project);
    await tick();
    expect(mockGet).toHaveBeenCalledOnce();
  });

  it('keeps the activity view mounted during same-owner renewal and transient detail errors, but clears it after native denial', async () => {
    const pending = Promise.withResolvers<typeof project>();
    const log = { id: 1, created_at: '2026-11-06T00:00:00Z', project_id: project.id, user_id: 'user-a', username: 'keep-user', resource_type: 'instance', resource_id: 'vm-a', resource_name: 'VM A', action: 'create', status: 'success', error_message: null, extra: null };
    let primaryReads = 0;
    mockGet.mockImplementation((path: string) => {
      if (path.includes('/activity?')) return Promise.resolve([log]);
      if (path.includes('/members?')) return Promise.resolve([]);
      return ++primaryReads === 1 ? Promise.resolve(project) : pending.promise;
    });
    render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    await screen.findByRole('heading', { name: project.name });
    await fireEvent.click(screen.getByRole('button', { name: ti('projectDetail.activityTab') }));
    await screen.findByText('keep-user');
    const search = screen.getByRole('searchbox', { name: tc('table.search') }) as HTMLInputElement;
    await fireEvent.input(search, { target: { value: '^keep-user$' } });
    auth.update(state => ({ ...state, token: 'renewed-token' }));
    await tick();
    expect(search.isConnected).toBe(true); expect(search.value).toBe('^keep-user$');
    pending.resolve(project);
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/api/v1/admin/projects/project-1/members?domain_id=domain-a', 'renewed-token', 'admin-project'));
    expect(screen.getByRole('searchbox', { name: tc('table.search') })).toBe(search);
    mockGet.mockImplementation((path: string) => path.includes('/activity?') ? Promise.resolve([log]) : Promise.reject(new Error('temporary detail failure')));
    auth.update(state => ({ ...state, token: 'renewed-again' }));
    await screen.findByText(ti('projectDetail.loadFailed'));
    expect(search.isConnected).toBe(true); expect(search.value).toBe('^keep-user$');
    mockGet.mockImplementation((path: string) => path.includes('/activity?') ? Promise.resolve([log]) : Promise.reject(new ApiError(403, 'detail denied')));
    auth.update(state => ({ ...state, token: 'denied-token' }));
    await screen.findByText('detail denied');
    expect(search.isConnected).toBe(false);
    expect(screen.queryByRole('heading', { name: project.name })).toBeNull();
  });
});
