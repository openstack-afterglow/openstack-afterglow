vi.mock('$lib/api/client', () => ({
  api: {
    get: vi.fn(async (path: string) => {
      if (path === '/api/v1/admin/all-loadbalancers') {
        return [
          { id: 'lb-1', name: 'user-lb', status: 'ACTIVE', operating_status: 'ONLINE', vip_address: '192.0.2.10', project_id: 'proj-1', tags: [] },
          { id: 'lb-2', name: 'drover-lb', status: 'ACTIVE', operating_status: 'ONLINE', vip_address: '192.0.2.11', project_id: 'proj-1', tags: ['drover.managed=true', 'drover.resource_type=load_balancer'] },
        ];
      }
      if (path === '/api/v1/loadbalancers/lb-2') {
        return { id: 'lb-2', name: 'drover-lb', description: '', status: 'ACTIVE', operating_status: 'ONLINE', vip_address: '192.0.2.11', tags: ['drover.managed=true', 'drover.resource_type=load_balancer'] };
      }
      if (path.endsWith('/listeners') || path.endsWith('/pools')) return [];
      return {};
    }),
    delete: vi.fn(async () => undefined),
  },
  ApiError: class ApiError extends Error { status = 500; },
}));

vi.mock('$lib/stores/confirm.svelte', () => ({
  confirmDialog: vi.fn(async () => true),
}));

import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '$lib/api/client';
import { auth } from '$lib/stores/auth';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import LoadBalancerDetailPanel from '$lib/components/LoadBalancerDetailPanel.svelte';
import LbDetailHeader from '$lib/components/dashboard/loadbalancers/LbDetailHeader.svelte';
import AdminLoadBalancerPage from '../+page.svelte';

const ordinaryLb = {
  id: 'lb-1',
  name: 'user-lb',
  status: 'ACTIVE',
  operating_status: 'ONLINE',
  vip_address: '10.0.0.1',
  vip_subnet_id: null,
  tags: [],
};
const protectedLb = {
  id: 'lb-2',
  name: 'drover-lb',
  status: 'ACTIVE',
  operating_status: 'ONLINE',
  vip_address: '10.0.0.2',
  vip_subnet_id: null,
  tags: ['drover.managed=true', 'drover.resource_type=load_balancer'],
};

function setAdminAuth() {
  auth.set({
    token: 'admin-token',
    refreshToken: null,
    accessExpiresAt: null,
    userId: 'admin',
    username: 'admin',
    projectId: 'admin-proj',
    projectName: 'admin',
    availableProjects: [],
    roles: ['admin'],
    isSystemAdmin: true,
    federated: false,
  });
}

describe('Admin LoadBalancer Page and Protection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAdminAuth();
  });

  it('selects ordinary load balancers in bulk and keeps Drover resources unavailable', async () => {
    render(AdminLoadBalancerPage);

    const userLbCheckbox = await screen.findByRole('checkbox', { name: 'user-lb 선택' });
    expect((userLbCheckbox as HTMLInputElement).disabled).toBe(false);

    const droverLbCheckbox = screen.getByRole('checkbox', { name: 'drover-lb 선택' });
    expect((droverLbCheckbox as HTMLInputElement).disabled).toBe(true);
    expect(droverLbCheckbox.getAttribute('title')).toContain('일괄 삭제 불가');

    await fireEvent.click(screen.getByRole('checkbox', { name: '전체 로드밸런서 선택' }).closest('label')!);
    expect((userLbCheckbox as HTMLInputElement).checked).toBe(true);
    expect((droverLbCheckbox as HTMLInputElement).checked).toBe(false);
    expect(await screen.findByRole('region', { name: '선택한 로드밸런서 일괄 작업' })).toBeTruthy();
  });

  it('labels only Drover-managed detail deletion as forced', async () => {
    const { rerender } = render(LbDetailHeader, {
      props: { lb: ordinaryLb, saving: false, onDelete: vi.fn() },
    });
    expect(screen.getByRole('button', { name: '삭제' })).toBeTruthy();

    await rerender({ lb: protectedLb, saving: false, onDelete: vi.fn() });
    expect(screen.getByRole('button', { name: '강제 삭제' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
  });

  it('force-deletes a Drover resource through the existing endpoint after the stronger warning', async () => {
    const onDeleted = vi.fn();
    render(LoadBalancerDetailPanel, {
      props: { lbId: 'lb-2', onDeleted },
    });

    await fireEvent.click(await screen.findByRole('button', { name: '강제 삭제' }));

    await waitFor(() => {
      expect(confirmDialog).toHaveBeenCalledTimes(1);
      expect(api.delete).toHaveBeenCalledWith('/api/v1/loadbalancers/lb-2', 'admin-token', 'admin-proj');
      expect(onDeleted).toHaveBeenCalledTimes(1);
    });
    const confirmMessage = vi.mocked(confirmDialog).mock.calls[0][0];
    expect(confirmMessage).toContain('Drover가 관리하는');
    expect(confirmMessage).toContain('클러스터가 손상되거나');
    expect(confirmMessage).toContain('정말로 강제 삭제하시겠습니까?');
  });
});
