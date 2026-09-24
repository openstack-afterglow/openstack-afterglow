import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	patch: vi.fn(),
	delete: vi.fn(),
	downloadBlob: vi.fn(),
	downloadBlobAs: vi.fn(),
	toDataURL: vi.fn(),
	toastSuccess: vi.fn(),
	toastError: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({
	api: {
		get: mocks.get,
		post: mocks.post,
		patch: mocks.patch,
		delete: mocks.delete,
		downloadBlob: mocks.downloadBlob,
	},
	ApiError: class ApiError extends Error {
		status = 500;
	},
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-1', projectId: 'project-1' }),
}));
vi.mock('$lib/config/site', () => ({
	siteConfig: writable({ services: { waygate: true } }),
}));
vi.mock('$lib/stores/toast', () => ({
	toast: { success: mocks.toastSuccess, error: mocks.toastError },
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));
vi.mock('$lib/utils/downloadBlob', () => ({ downloadBlobAs: mocks.downloadBlobAs }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 15,
		intervalOptions: [10, 15, 30, 60],
	}),
}));
vi.mock('qrcode', () => ({ default: { toDataURL: mocks.toDataURL } }));

import Page from '../+page.svelte';

const server = {
	id: 'server-1',
	project_id: 'project-1',
	name: 'tenant-gateway',
	status: 'ACTIVE',
	status_reason: null,
	server_vm_id: 'vm-1',
	endpoint_ip: '198.51.100.12',
	listen_port: 51820,
	tunnel_cidr: '10.240.0.0/24',
	dns: '1.1.1.1',
	mtu: 1420,
	server_public_key: 'server-public-key',
	created_at: '2026-09-20T00:00:00Z',
	updated_at: '2026-09-20T00:00:00Z',
	last_status_reported_at: '2026-09-20T00:00:10Z',
	peer_count: 1,
};

const client = {
	id: 'client-1',
	server_id: 'server-1',
	project_id: 'project-1',
	name: 'operator-laptop',
	enabled: true,
	public_key: 'client-public-key',
	tunnel_ip: '10.240.0.2',
	allowed_ips: ['10.240.0.0/24'],
	dns: '1.1.1.1',
	created_at: '2026-09-20T00:00:00Z',
	updated_at: '2026-09-20T00:00:00Z',
	online: true,
	last_handshake_at: '2026-09-20T00:00:10Z',
	rx_bytes: 128,
	tx_bytes: 256,
};

const networks = [
	{
		id: 'net-empty',
		name: 'empty-net',
		status: 'ACTIVE',
		subnets: [],
		is_external: false,
		is_shared: false,
		project_id: 'project-1',
	},
	{
		id: 'net-private',
		name: 'private-net',
		status: 'ACTIVE',
		subnets: ['subnet-app'],
		is_external: false,
		is_shared: false,
		project_id: 'project-1',
	},
	{
		id: 'net-public',
		name: 'public-net',
		status: 'ACTIVE',
		subnets: ['subnet-public'],
		is_external: true,
		is_shared: true,
		project_id: null,
	},
];

function installApiResponses() {
	mocks.get.mockImplementation((path: string) => {
		if (path === '/api/v1/waygate/servers') return Promise.resolve([server]);
		if (path === '/api/v1/waygate/servers/server-1/clients') return Promise.resolve([client]);
		if (path === '/api/v1/waygate/servers/server-1/networks') return Promise.resolve([]);
		if (path === '/api/v1/networks') return Promise.resolve(networks);
		if (path === '/api/v1/networks/net-empty') {
			return Promise.resolve({ ...networks[0], subnet_details: [], routers: [] });
		}
		if (path === '/api/v1/networks/net-private') {
			return Promise.resolve({
				...networks[1],
				subnet_details: [
					{
						id: 'subnet-app',
						name: 'app-subnet',
						cidr: '10.20.0.0/24',
						gateway_ip: '10.20.0.1',
						dhcp_enabled: true,
					},
				],
				routers: [],
			});
		}
		throw new Error(`unexpected GET ${path}`);
	});
	mocks.post.mockResolvedValue({
		id: 7,
		server_id: 'server-1',
		project_id: 'project-1',
		network_id: 'net-private',
		subnet_id: 'subnet-app',
		port_id: 'port-1',
		cidr: '10.20.0.0/24',
		nat_mode: 'snat',
		status: 'ACTIVE',
		created_at: '2026-09-20T00:00:00Z',
		updated_at: '2026-09-20T00:00:00Z',
	});
	const configBlob = new Blob(['[Interface]\nPrivateKey = secret']);
	Object.defineProperty(configBlob, 'text', {
		value: vi.fn().mockResolvedValue('[Interface]\nPrivateKey = secret'),
	});
	mocks.downloadBlob.mockResolvedValue({ blob: configBlob, filename: 'operator-laptop.conf' });
	mocks.toDataURL.mockResolvedValue('data:image/png;base64,wireguard');
}

async function openServerPanel() {
	render(Page);
	expect(await screen.findByText('tenant-gateway')).toBeTruthy();
	expect(screen.getByText('ACTIVE')).toBeTruthy();
	await fireEvent.click(screen.getByText('tenant-gateway'));
	expect(await screen.findByText('operator-laptop')).toBeTruthy();
}

beforeEach(() => {
	Element.prototype.animate = vi.fn().mockReturnValue({
		finished: Promise.resolve(),
		cancel: vi.fn(),
		play: vi.fn(),
	});
	window.matchMedia = vi.fn().mockImplementation((query: string) => ({
		matches: false,
		media: query,
		onchange: null,
		addListener: vi.fn(),
		removeListener: vi.fn(),
		addEventListener: vi.fn(),
		removeEventListener: vi.fn(),
		dispatchEvent: vi.fn(),
	}));
	vi.clearAllMocks();
	installApiResponses();
});

describe('Waygate dashboard', () => {
	it('shows servers and status, then attaches an explicit tenant subnet', async () => {
		await openServerPanel();

		await fireEvent.click(screen.getByRole('button', { name: '+ 네트워크 연결' }));
		await vi.waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/networks', 'token-1', 'project-1'));

		const networkSelect = screen.getByRole('button', { name: '연결할 네트워크 선택' });
		await fireEvent.click(networkSelect);
		expect(screen.queryByRole('option', { name: /public-net/ })).toBeNull();
		await fireEvent.click(screen.getByRole('option', { name: /empty-net/ }));
		expect(await screen.findByText('선택한 네트워크에 연결 가능한 서브넷이 없습니다.')).toBeTruthy();
		expect((screen.getByRole('button', { name: '연결' }) as HTMLButtonElement).disabled).toBe(true);

		await fireEvent.click(networkSelect);
		await fireEvent.click(screen.getByRole('option', { name: /private-net/ }));
		expect((await screen.findByRole('button', { name: '연결할 서브넷 선택' })).textContent).toContain('app-subnet');

		const attach = screen.getByRole('button', { name: '연결' });
		expect((attach as HTMLButtonElement).disabled).toBe(false);
		await fireEvent.click(attach);

		await vi.waitFor(() => {
			expect(mocks.post).toHaveBeenCalledWith(
				'/api/v1/waygate/servers/server-1/networks',
				{ network_id: 'net-private', subnet_id: 'subnet-app', nat_mode: 'snat' },
				'token-1',
				'project-1'
			);
		});
	});

	it('downloads client config and renders a QR code from the same config', async () => {
		await openServerPanel();

		await fireEvent.click(screen.getByRole('button', { name: '.conf 다운로드' }));
		await vi.waitFor(() => expect(mocks.downloadBlobAs).toHaveBeenCalledWith(expect.any(Blob), 'operator-laptop.conf'));

		await fireEvent.click(screen.getByRole('button', { name: 'QR' }));
		const qrImage = await screen.findByRole('img', { name: 'WireGuard 설정 QR 코드' });
		expect(qrImage.getAttribute('src')).toBe('data:image/png;base64,wireguard');
		expect(mocks.toDataURL).toHaveBeenCalledWith('[Interface]\nPrivateKey = secret', {
			errorCorrectionLevel: 'M',
			margin: 2,
			width: 320,
		});
	});
});
