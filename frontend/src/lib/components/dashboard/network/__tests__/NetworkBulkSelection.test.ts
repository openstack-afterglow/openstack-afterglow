vi.mock('$lib/api/client', () => ({
  api: {
    get: vi.fn(async (path: string) => path === '/api/v1/loadbalancers'
      ? [
          { id: 'lb-1', name: 'edge', status: 'ACTIVE', operating_status: 'ONLINE', vip_address: '192.0.2.10', vip_subnet_id: null, tags: [] },
          { id: 'lb-2', name: 'drover-k3s', status: 'ACTIVE', operating_status: 'ONLINE', vip_address: '192.0.2.11', vip_subnet_id: null, tags: ['drover.managed=true', 'drover.resource_type=load_balancer'] },
        ]
      : []),
    delete: vi.fn(async () => undefined),
  },
  ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/api/waygate', () => ({
  listServers: vi.fn(async () => [{
    id: 'waygate-1', project_id: 'project', name: 'gateway', status: 'ACTIVE', status_reason: null,
    server_vm_id: null, endpoint_ip: '192.0.2.20', listen_port: 51820, tunnel_cidr: '10.0.0.0/24',
    dns: null, mtu: null, server_public_key: null, created_at: null, updated_at: null,
    last_status_reported_at: null, peer_count: 0,
  }]),
  deleteServer: vi.fn(async () => undefined),
  listClients: vi.fn(async () => []),
}));
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import NetworksTableCard from '../networks/NetworksTableCard.svelte';
import FloatingIpCard from '../networks/FloatingIpCard.svelte';
import RouterCardGrid from '$lib/components/network/routers/RouterCardGrid.svelte';
import SecurityGroupList from '../security-groups/SecurityGroupList.svelte';
import LoadBalancerPage from '../../../../../routes/dashboard/network/loadbalancers/+page.svelte';
import WaygatePage from '../../../../../routes/dashboard/network/waygate/+page.svelte';
import type { Network, FloatingIp, Router } from '$lib/types/networks';
import type { SecurityGroup } from '$lib/types/securityGroup';

const networks: Network[] = [
  { id: 'private-1', name: 'private', status: 'ACTIVE', subnets: [], is_external: false, is_shared: false },
  { id: 'external-1', name: 'public', status: 'ACTIVE', subnets: [], is_external: true, is_shared: false },
  { id: 'shared-1', name: 'shared', status: 'ACTIVE', subnets: [], is_external: false, is_shared: true },
];
const fips: FloatingIp[] = [{ id: 'fip-1', floating_ip_address: '203.0.113.10', status: 'DOWN', fixed_ip_address: null, port_id: null }];
const routers: Router[] = [{ id: 'router-1', name: 'router', status: 'ACTIVE', external_gateway_network_id: null, connected_subnet_ids: [] }];
const groups: SecurityGroup[] = [
  { id: 'sg-1', name: 'default', description: 'default group', rules: [] } as SecurityGroup,
  { id: 'sg-2', name: 'custom', description: 'custom group', rules: [] } as SecurityGroup,
];

const common = {
  selectedIds: new Set<string>(),
  selectionDisabled: false,
  onToggleSelect: vi.fn(),
  onToggleAll: vi.fn(),
};

describe('network bulk selection controls', () => {
  it('excludes shared and external networks from mutation selection and menus', async () => {
    const onToggleAll = vi.fn();
    render(NetworksTableCard, {
      networks,
      defaultNetworkId: null,
      deleting: null,
      settingDefault: null,
      selectableIds: new Set(['private-1']),
      ...common,
      onToggleAll,
      onOpenPanel: vi.fn(),
      onSetDefault: vi.fn(),
      onDelete: vi.fn(),
    });
    expect((screen.getByRole('checkbox', { name: 'public 선택' }) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole('checkbox', { name: 'shared 선택' }) as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByRole('button', { name: 'shared 네트워크 작업' })).toBeNull();
    const selectAll = screen.getByRole('checkbox', { name: '전체 네트워크 선택' });
    expect((selectAll as HTMLInputElement).disabled).toBe(false);
    await fireEvent.click(selectAll.closest('label')!);
    expect(onToggleAll).toHaveBeenCalledOnce();
  });

  it('isolates floating IP checkbox clicks from card actions', async () => {
    const onToggleSelect = vi.fn();
    render(FloatingIpCard, {
      floatingIps: fips,
      hasExternalNetwork: true,
      selectedIds: new Set<string>(),
      selectableIds: new Set(['fip-1']),
      selectionDisabled: false,
      onToggleSelect,
      onToggleAll: vi.fn(),
      onAllocateClick: vi.fn(),
    });
    await fireEvent.click(screen.getByRole('checkbox', { name: '203.0.113.10 선택' }).closest('label')!);
    expect(onToggleSelect).toHaveBeenCalledWith('fip-1');
  });

  it('renders router and security group selection toolbars', () => {
    const { unmount } = render(RouterCardGrid, {
      routers,
      externalNetworkName: () => '',
      selectedIds: new Set<string>(),
      selectableIds: new Set(['router-1']),
      selectionDisabled: false,
      onToggleSelect: vi.fn(),
      onToggleAll: vi.fn(),
      onOpen: vi.fn(),
    });
    expect(screen.getByRole('checkbox', { name: '전체 라우터 선택' })).toBeTruthy();
    unmount();
    render(SecurityGroupList, {
      groups,
      selectedSg: null,
      selectedIds: new Set<string>(),
      selectableIds: new Set(['sg-2']),
      selectionDisabled: false,
      onToggleSelect: vi.fn(),
      onToggleAll: vi.fn(),
    });
    expect(screen.getByRole('checkbox', { name: '전체 보안 그룹 선택' })).toBeTruthy();
    expect((screen.getByRole('checkbox', { name: 'default 선택' }) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole('checkbox', { name: 'custom 선택' }) as HTMLInputElement).disabled).toBe(false);
  });

  it('renders load balancer route selection controls and excludes protected resources', async () => {
    auth.set({
      token: 'token',
      refreshToken: null,
      accessExpiresAt: null,
      userId: 'user',
      username: 'user',
      projectId: 'project',
      projectName: 'project',
      availableProjects: [],
      roles: [],
      isSystemAdmin: false,
      federated: false,
    });
    render(LoadBalancerPage);
    const ordinaryCheckbox = await screen.findByRole('checkbox', { name: 'edge 선택' });
    expect((ordinaryCheckbox as HTMLInputElement).disabled).toBe(false);
    const protectedCheckbox = screen.getByRole('checkbox', { name: 'drover-k3s 선택' });
    expect((protectedCheckbox as HTMLInputElement).disabled).toBe(true);

    const selectAll = screen.getByRole('checkbox', { name: '전체 로드밸런서 선택' });
    selectAll.click();
    expect(await screen.findByRole('region', { name: '선택한 로드밸런서 일괄 작업' })).toBeTruthy();
  });

  it('renders Waygate server selection controls', async () => {
    auth.set({
      token: 'token',
      refreshToken: null,
      accessExpiresAt: null,
      userId: 'user',
      username: 'user',
      projectId: 'project',
      projectName: 'project',
      availableProjects: [],
      roles: [],
      isSystemAdmin: false,
      federated: false,
    });
    render(WaygatePage);
    const checkbox = await screen.findByRole('checkbox', { name: 'gateway 선택' });
    expect((checkbox as HTMLInputElement).disabled).toBe(false);
    const selectAll = screen.getByRole('checkbox', { name: '전체 Waygate 서버 선택' });
    selectAll.click();
    expect(await screen.findByRole('region', { name: '선택한 Waygate 서버 일괄 작업' })).toBeTruthy();
    expect(screen.getByText('gateway')).toBeTruthy();
  });
});
