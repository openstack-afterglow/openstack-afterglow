import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock('$app/stores', () => ({ page: writable({ params: { id: 'project-1' }, data: {} }) }));
vi.mock('$lib/api/client', () => ({
  api: { get: mockGet },
  ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'admin-project' }) }));
import Page from '$lib/components/admin/projects/AdminProjectDetailPage.svelte';

const project = { id: 'project-1', name: 'Project One', description: 'Primary content', enabled: true, domain_id: 'domain-a', created_at: null };

beforeEach(() => { mockGet.mockReset(); });
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
});
