import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import NetworksTableCard from '../networks/NetworksTableCard.svelte';
import type { Network } from '$lib/types/networks';
import { createTableView } from '$lib/utils/tableView.svelte';

const singleCidrNet: Network = {
  id: 'net-single',
  name: 'single-cidr-net',
  status: 'ACTIVE',
  subnets: ['subnet-1'],
  cidrs: ['192.168.1.0/24'],
  is_external: false,
  is_shared: false,
};

const multiCidrNet: Network = {
  id: 'net-multi',
  name: 'multi-cidr-net',
  status: 'ACTIVE',
  subnets: ['subnet-1', 'subnet-2'],
  cidrs: ['192.168.1.0/24', '10.0.0.0/16'],
  is_external: false,
  is_shared: false,
};

const missingCidrNet: Network = {
  id: 'net-missing',
  name: 'missing-cidr-net',
  status: 'ACTIVE',
  subnets: [],
  is_external: false,
  is_shared: false,
};

const emptyCidrNet: Network = {
  id: 'net-empty',
  name: 'empty-cidr-net',
  status: 'ACTIVE',
  subnets: [],
  cidrs: [],
  is_external: false,
  is_shared: false,
};

const commonProps = {
  view: createTableView({ rows: () => [singleCidrNet, multiCidrNet, missingCidrNet, emptyCidrNet], columns: () => [
    { key: 'name', label: 'Name', value: row => row.name },
    { key: 'cidr', label: 'CIDR', value: row => row.cidrs?.join(', ') },
    { key: 'type', label: 'Type', value: row => row.is_external ? 'external' : row.is_shared ? 'shared' : 'internal' },
    { key: 'subnets', label: 'Subnets', value: row => row.subnets.length },
    { key: 'status', label: 'Status', value: row => row.status },
  ] }),
  defaultNetworkId: null,
  deleting: null,
  settingDefault: null,
  selectedIds: new Set<string>(),
  selectableIds: new Set<string>(['net-single', 'net-multi', 'net-missing', 'net-empty']),
  selectionDisabled: false,
  onToggleSelect: vi.fn(),
  onToggleAll: vi.fn(),
  onOpenPanel: vi.fn(),
  onSetDefault: vi.fn(),
  onDelete: vi.fn(),
};

describe('NetworksTableCard CIDR rendering & selection regressions', () => {
  it('renders single CIDR, multiple CIDRs, and missing/empty CIDRs correctly', () => {
    const { container } = render(NetworksTableCard, {
      ...commonProps,
      networks: [singleCidrNet, multiCidrNet, missingCidrNet, emptyCidrNet],
    });

    expect(screen.getByText('192.168.1.0/24')).toBeTruthy();
    expect(screen.getByText('192.168.1.0/24, 10.0.0.0/16')).toBeTruthy();

    const singleElem = screen.getByText('192.168.1.0/24');
    expect(singleElem.getAttribute('title')).toBe('192.168.1.0/24');

    const multiElem = screen.getByText('192.168.1.0/24, 10.0.0.0/16');
    expect(multiElem.getAttribute('title')).toBe('192.168.1.0/24, 10.0.0.0/16');

    // Em dash cells for missing and empty CIDR networks
    const dashCells = container.querySelectorAll('.font-mono');
    const emDashTexts = Array.from(dashCells).filter((el) => el.textContent?.trim() === '—');
    expect(emDashTexts.length).toBeGreaterThanOrEqual(2);
  });

  it('preserves selection behavior and panel trigger with CIDR rendering', async () => {
    const onToggleSelect = vi.fn();
    const onOpenPanel = vi.fn();

    render(NetworksTableCard, {
      ...commonProps,
      networks: [singleCidrNet, multiCidrNet],
      onToggleSelect,
      onOpenPanel,
    });

    const checkbox = screen.getByRole('checkbox', { name: 'single-cidr-net 선택' });
    await fireEvent.click(checkbox);
    expect(onToggleSelect).toHaveBeenCalledWith('net-single');

    const nameBtn = screen.getByText('multi-cidr-net');
    await fireEvent.click(nameBtn);
    expect(onOpenPanel).toHaveBeenCalledWith('net-multi');
  });
});
