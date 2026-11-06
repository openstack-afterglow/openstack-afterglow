vi.mock('$lib/stores/servicePermissions', () => ({
  serviceCapabilities: writable<(leaf: string) => boolean>(() => false),
  observedProjectPermissions: writable<PermissionState>({ permissions: null, loading: false, error: '' }),
}));
vi.mock('$lib/api/client', () => ({
  api: {
    get: vi.fn(async (path: string) => path === '/api/v1/loadbalancers'
      ? [
          { id: 'lb-1', name: 'edge', status: 'ACTIVE', operating_status: 'ONLINE', vip_address: '192.0.2.10', vip_subnet_id: null, tags: [] },
          { id: 'lb-2', name: 'drover-k3s', status: 'ACTIVE', operating_status: 'ONLINE', vip_address: '192.0.2.11', vip_subnet_id: null, tags: ['drover.managed=true', 'drover.resource_type=load_balancer'] },
        ]
      : []),
    delete: vi.fn(async () => undefined),
    withExperience() { return this; },
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
import { writable, type Writable } from 'svelte/store';
import { observedProjectPermissions, serviceCapabilities } from '$lib/stores/servicePermissions';
import type { PermissionState } from '$lib/stores/servicePermissions';
import { auth } from '$lib/stores/auth';
import NetworksTableCard from '../networks/NetworksTableCard.svelte';
import FloatingIpCard from '../networks/FloatingIpCard.svelte';
import RouterCardGrid from '$lib/components/network/routers/RouterCardGrid.svelte';
import SecurityGroupList from '../security-groups/SecurityGroupList.svelte';
import LoadBalancerPage from '../../../../../routes/dashboard/network/loadbalancers/+page.svelte';
import WaygatePage from '../../../../../routes/dashboard/network/waygate/+page.svelte';
import type { Network, FloatingIp, Router } from '$lib/types/networks';
import type { SecurityGroup } from '$lib/types/securityGroup';
import { createTableView } from '$lib/utils/tableView.svelte';
import { tick } from 'svelte';
import { t as tc } from '$lib/i18n/ns/common';
import { t as tn } from '$lib/i18n/ns/network-resources';
import LbPoolSection from '$lib/components/dashboard/loadbalancers/id/LbPoolSection.svelte';
import { memberColumns } from '$lib/utils/loadBalancerTableColumns';

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
  it('excludes shared and external networks from mutation selection and actions', async () => {
    const onToggleAll = vi.fn();
    render(NetworksTableCard, {
      networks,
      view: createTableView({ rows: () => networks, columns: () => [
        { key: 'name', label: 'Name', value: row => row.name },
        { key: 'cidr', label: 'CIDR', value: row => row.cidrs?.join(', ') },
        { key: 'type', label: 'Type', value: row => row.is_external ? 'external' : row.is_shared ? 'shared' : 'internal' },
        { key: 'subnets', label: 'Subnets', value: row => row.subnets.length },
        { key: 'status', label: 'Status', value: row => row.status },
      ] }),
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
    await fireEvent.click(screen.getByRole('button', { name: 'shared 네트워크 작업' }));
    expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
    expect(screen.queryByRole('button', { name: '기본 네트워크로 설정' })).toBeNull();
    await fireEvent.keyDown(document, { key: 'Escape' });
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
      federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false,
    });
    render(LoadBalancerPage);
    const ordinaryCheckbox = await screen.findByRole('checkbox', { name: 'edge 선택' });
    expect((ordinaryCheckbox as HTMLInputElement).disabled).toBe(false);
    const protectedCheckbox = screen.getByRole('checkbox', { name: 'drover-k3s 선택' });
    expect((protectedCheckbox as HTMLInputElement).disabled).toBe(true);

    const selectAll = screen.getByRole('checkbox', { name: '전체 로드밸런서 선택' });
    selectAll.click();
    expect(await screen.findByRole('region', { name: '선택한 로드밸런서 일괄 작업' })).toBeTruthy();
    await fireEvent.input(screen.getByRole('searchbox'), { target: { value: '^drover-k3s$' } });
    expect(screen.queryByRole('checkbox', { name: 'edge 선택' })).toBeNull();
    expect(screen.getByRole('checkbox', { name: 'drover-k3s 선택' })).toBeTruthy();
    expect(screen.queryByRole('region', { name: '선택한 로드밸런서 일괄 작업' })).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: tc('table.sortColumn', { column: tn('network.labels.name'), direction: tc('table.none') }) }));
    const statusFilter = tc('table.filterColumn', { column: tn('network.labels.status') });
    await fireEvent.click(screen.getByRole('button', { name: statusFilter }));
    await fireEvent.click(screen.getByRole('button', { name: tc('table.selectNone') }));
    await fireEvent.keyDown(screen.getByRole('dialog', { name: statusFilter }), { key: 'Escape' });
    auth.update(state => ({ ...state, token: 'rotated-token', refreshToken: 'rotated-refresh' }));
    await tick();
    expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('^drover-k3s$');
    expect(screen.getByRole('button', { name: tc('table.sortColumn', { column: tn('network.labels.name'), direction: tc('table.ascending') }) })).toBeTruthy();
    expect(screen.queryByRole('checkbox', { name: 'drover-k3s 선택' })).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: statusFilter }));
    await fireEvent.click(screen.getByRole('button', { name: tc('table.resetFilter') }));
    await fireEvent.keyDown(screen.getByRole('dialog', { name: statusFilter }), { key: 'Escape' });
    expect(screen.getByRole('checkbox', { name: 'drover-k3s 선택' })).toBeTruthy();
    await fireEvent.input(screen.getByRole('searchbox'), { target: { value: '[' } });
    expect(screen.queryByRole('checkbox', { name: 'drover-k3s 선택' })).toBeNull();
    expect(screen.getByRole('searchbox').getAttribute('aria-invalid')).toBe('true');
  });

  it('renders Waygate server selection controls', async () => {
    (serviceCapabilities as Writable<(leaf: string) => boolean>).set((leaf) => leaf === 'waygate-gateways_admin');
    (observedProjectPermissions as Writable<PermissionState>).set({
      permissions: { is_owner: false, is_manager: false, can_write: true, service_permissions: { waygate: ['waygate-gateways_admin'] } },
      loading: false, error: '',
    });
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
      federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false,
    });
    render(WaygatePage);
    const checkbox = await screen.findByRole('checkbox', { name: 'gateway 선택' });
    expect((checkbox as HTMLInputElement).disabled).toBe(false);
    const selectAll = screen.getByRole('checkbox', { name: '전체 Waygate 서버 선택' });
    selectAll.click();
    expect(await screen.findByRole('region', { name: '선택한 Waygate 서버 일괄 작업' })).toBeTruthy();
    expect(screen.getByText('gateway')).toBeTruthy();
  });

  it('retains member view state when a selected pool row disappears and returns', async () => {
    const pools = [{ id: 'pool-1', name: 'pool', protocol: 'HTTP', lb_algorithm: 'ROUND_ROBIN', status: 'ACTIVE' }];
    const members = [{ id: 'member-1', address: '10.0.0.2', protocol_port: 80, weight: 1, status: 'ACTIVE' }];
    const memberView = createTableView({ rows: () => members, columns: memberColumns });
    const props = {
      pools, members, memberView, selectedPoolId: 'pool-1', membersLoading: false,
      saving: false, error: '', addingMember: false, addMemberError: '',
      onAddPool: vi.fn(async () => true), onDeletePool: vi.fn(async () => {}),
      onSelectPool: vi.fn(), onAddMember: vi.fn(async () => true), onRemoveMember: vi.fn(async () => {}),
    };
    const panel = render(LbPoolSection, props);
    const address = tn('lb.form.ipAddress');
    await fireEvent.click(screen.getByRole('button', { name: tc('table.sortColumn', { column: address, direction: tc('table.none') }) }));
    const addressFilter = tc('table.filterColumn', { column: address });
    await fireEvent.click(screen.getByRole('button', { name: addressFilter }));
    await fireEvent.click(screen.getByRole('button', { name: tc('table.selectNone') }));
    await fireEvent.keyDown(screen.getByRole('dialog', { name: addressFilter }), { key: 'Escape' });
    await panel.rerender({ ...props, pools: [] });
    expect(screen.queryByText('10.0.0.2:80')).toBeNull();
    await panel.rerender({ ...props, pools: structuredClone(pools) });
    expect(screen.getByRole('button', { name: tc('table.sortColumn', { column: address, direction: tc('table.ascending') }) })).toBeTruthy();
    expect(screen.queryByText('10.0.0.2:80')).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: addressFilter }));
    await fireEvent.click(screen.getByRole('button', { name: tc('table.resetFilter') }));
    await fireEvent.keyDown(screen.getByRole('dialog', { name: addressFilter }), { key: 'Escape' });
    expect(screen.getByText('10.0.0.2:80')).toBeTruthy();
  });
});
