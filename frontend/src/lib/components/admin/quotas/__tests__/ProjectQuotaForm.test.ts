import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Quotas } from '$lib/types/quotas';
import ProjectQuotaForm from '../ProjectQuotaForm.svelte';

const sampleQuotas: Quotas = {
	compute: {
		instances: { limit: 10, in_use: 2 },
		cores: { limit: 20, in_use: 4 },
		ram: { limit: 51200, in_use: 2048 },
		metadata_items: { limit: 128, in_use: 0 },
		key_pairs: { limit: 100, in_use: 3 },
		server_groups: { limit: 10, in_use: 1 },
		server_group_members: { limit: 10, in_use: 0 },
		injected_files: { limit: 5, in_use: 0 },
		injected_file_content_bytes: { limit: 10240, in_use: 0 },
		injected_file_path_bytes: { limit: 255, in_use: 0 },
	},
	volume: {
		volumes: { limit: 10, in_use: 3 },
		snapshots: { limit: 5, in_use: 1 },
		gigabytes: { limit: 1000, in_use: 150 },
	},
	network: {
		network: { limit: 10, in_use: 1 },
		subnet: { limit: 10, in_use: 1 },
		port: { limit: 50, in_use: 5 },
		router: { limit: 5, in_use: 1 },
		floatingip: { limit: 2, in_use: 1 },
		security_group: { limit: 20, in_use: 4 },
		security_group_rule: { limit: 100, in_use: 12 },
	},
	file_storage: {
		shares: { limit: 5, in_use: 1 },
		gigabytes: { limit: 500, in_use: 50 },
		snapshots: { limit: 10, in_use: 2 },
		snapshot_gigabytes: { limit: 250, in_use: 20 },
		share_networks: { limit: 3, in_use: 1 },
		share_groups: { limit: 2, in_use: 0 },
		share_group_snapshots: { limit: 5, in_use: 0 },
	},
};

const unusedSave = async () => ({ success: false });

describe('ProjectQuotaForm', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('renders compute, volume, network, and file storage sections with actual in_use and limits', () => {
		render(ProjectQuotaForm, {
			quotas: sampleQuotas,
			projectId: 'proj-123',
			onSaveSection: unusedSave,
		});

		expect(screen.getByText('Compute 쿼터')).not.toBeNull();
		expect(screen.getByText('Volume 쿼터')).not.toBeNull();
		expect(screen.getByText('Network 쿼터')).not.toBeNull();
		expect(screen.getByText('File Storage (Manila) 쿼터')).not.toBeNull();

		// Assert usage in its owning provider, not just a matching number elsewhere.
		expect(within(screen.getByTestId('quota-section-compute')).getByText('사용: 2')).not.toBeNull();
		expect(within(screen.getByTestId('quota-section-compute')).getByText('사용: 2 GB')).not.toBeNull();
		expect(within(screen.getByTestId('quota-section-volume')).getByText('사용: 150 GB')).not.toBeNull();
		expect(within(screen.getByTestId('quota-section-file_storage')).getByText('사용: 50 GB')).not.toBeNull();
		expect(within(screen.getByTestId('quota-section-file_storage')).getByText('사용: 2')).not.toBeNull();

		// Inputs populated with current limits
		const instancesInput = screen.getByTestId('quota-compute-instances') as HTMLInputElement;
		expect(instancesInput.value).toBe('10');

		const volumeSnapshotsInput = screen.getByTestId('quota-volume-snapshots') as HTMLInputElement;
		expect(volumeSnapshotsInput.value).toBe('5');

		const networkFloatingIpInput = screen.getByTestId('quota-network-floatingip') as HTMLInputElement;
		expect(networkFloatingIpInput.value).toBe('2');

		const manilaSharesInput = screen.getByTestId('quota-file_storage-shares') as HTMLInputElement;
		expect(manilaSharesInput.value).toBe('5');
	});

	it('displays unlimited badge when limit is -1', () => {
		const quotasWithUnlimited: Quotas = {
			...sampleQuotas,
			network: {
				...sampleQuotas.network,
				floatingip: { limit: -1, in_use: 0 },
			},
		};

		render(ProjectQuotaForm, {
			quotas: quotasWithUnlimited,
			projectId: 'proj-123',
			onSaveSection: unusedSave,
		});

		const fipInput = screen.getByTestId('quota-network-floatingip') as HTMLInputElement;
		expect(fipInput.value).toBe('-1');
		expect(screen.getByText('무제한')).not.toBeNull();
	});

	it('visibly explains disabled Manila service and renders no inputs or save button when file_storage is null', () => {
		const quotasManilaDisabled: Quotas = {
			...sampleQuotas,
			file_storage: null,
		};

		render(ProjectQuotaForm, {
			quotas: quotasManilaDisabled,
			projectId: 'proj-123',
			onSaveSection: unusedSave,
		});

		expect(screen.getByText('파일 스토리지(Manila) 서비스가 활성화되어 있지 않습니다.')).not.toBeNull();
		expect(screen.queryByTestId('quota-file_storage-shares')).toBeNull();
		expect(screen.queryByTestId('save-file_storage-btn')).toBeNull();
	});

	it('visibly displays service error and omits inputs when a service lookup fails', () => {
		const quotasNetworkError: Quotas = {
			...sampleQuotas,
			network: null,
			errors: { network: 'Neutron API timeout' },
		};

		render(ProjectQuotaForm, {
			quotas: quotasNetworkError,
			projectId: 'proj-123',
			onSaveSection: unusedSave,
		});

		const networkAlert = within(screen.getByTestId('quota-section-network')).getByRole('alert');
		expect(within(networkAlert).getByText('Network 쿼터 서비스를 사용할 수 없습니다:')).not.toBeNull();
		expect(within(networkAlert).getByText('Neutron API timeout')).not.toBeNull();
		expect(screen.queryByTestId('quota-network-floatingip')).toBeNull();
		expect(screen.queryByTestId('save-network-btn')).toBeNull();
	});

	it('marks unsupported individual fields as disabled without fake zeros and excludes them from save', async () => {
		const onSaveSection = vi.fn().mockResolvedValue({ success: true, status: 'updated' });
		const quotasOmittedFields: Quotas = {
			...sampleQuotas,
			compute: {
				instances: { limit: 10, in_use: 2 },
				cores: { limit: 20, in_use: 4 },
				ram: { limit: 51200, in_use: 2048 },
				// metadata_items, key_pairs, injected_files etc. are omitted
			},
		};

		render(ProjectQuotaForm, {
			quotas: quotasOmittedFields,
			projectId: 'proj-123',
			onSaveSection,
		});

		// Unsupported field shows disabled input with placeholder and no fake zero
		const disabledInput = screen.getByTestId('quota-compute-injected_files-disabled') as HTMLInputElement;
		expect(disabledInput.disabled).toBe(true);

		// Modify a supported field
		const instancesInput = screen.getByTestId('quota-compute-instances');
		await fireEvent.input(instancesInput, { target: { value: '15' } });

		const saveBtn = screen.getByTestId('save-compute-btn');
		await fireEvent.click(saveBtn);

		expect(onSaveSection).toHaveBeenCalledWith('compute', { instances: 15 });
		// injected_files or other omitted fields must NEVER be in the payload
		expect(onSaveSection.mock.calls[0][1]).not.toHaveProperty('injected_files');
	});

	it('Network section save sends ONLY changed network keys via flat payload', async () => {
		const onSaveSection = vi.fn().mockResolvedValue({ success: true, status: 'updated' });

		render(ProjectQuotaForm, {
			quotas: sampleQuotas,
			projectId: 'proj-123',
			onSaveSection,
		});

		const sgInput = screen.getByTestId('quota-network-security_group');
		await fireEvent.input(sgInput, { target: { value: '30' } });

		const fipInput = screen.getByTestId('quota-network-floatingip');
		await fireEvent.input(fipInput, { target: { value: '5' } });

		const networkSaveBtn = screen.getByTestId('save-network-btn');
		await fireEvent.click(networkSaveBtn);

		expect(onSaveSection).toHaveBeenCalledTimes(1);
		expect(onSaveSection).toHaveBeenCalledWith('network', {
			security_group: 30,
			floatingip: 5,
		});
		// Must not include unchanged network fields like router, subnet, port
		expect(onSaveSection.mock.calls[0][1]).not.toHaveProperty('router');
		expect(onSaveSection.mock.calls[0][1]).not.toHaveProperty('subnet');
		expect(onSaveSection.mock.calls[0][1]).not.toHaveProperty('port');
	});

	it('Manila (File Storage) section save maps changed keys to share_ aliases in PUT payload', async () => {
		const onSaveSection = vi.fn().mockResolvedValue({ success: true, status: 'updated' });

		render(ProjectQuotaForm, {
			quotas: sampleQuotas,
			projectId: 'proj-123',
			onSaveSection,
		});

		const gbInput = screen.getByTestId('quota-file_storage-gigabytes');
		await fireEvent.input(gbInput, { target: { value: '800' } });

		const snapInput = screen.getByTestId('quota-file_storage-snapshots');
		await fireEvent.input(snapInput, { target: { value: '25' } });

		const snapGbInput = screen.getByTestId('quota-file_storage-snapshot_gigabytes');
		await fireEvent.input(snapGbInput, { target: { value: '400' } });

		const manilaSaveBtn = screen.getByTestId('save-file_storage-btn');
		await fireEvent.click(manilaSaveBtn);

		expect(onSaveSection).toHaveBeenCalledTimes(1);
		expect(onSaveSection).toHaveBeenCalledWith('file_storage', {
			share_gigabytes: 800,
			share_snapshots: 25,
			share_snapshot_gigabytes: 400,
		});
		// Unchanged Manila fields must not be included
		expect(onSaveSection.mock.calls[0][1]).not.toHaveProperty('shares');
		expect(onSaveSection.mock.calls[0][1]).not.toHaveProperty('share_networks');
	});

	it('Cinder (Volume) section save sends only changed volume fields including snapshots', async () => {
		const onSaveSection = vi.fn().mockResolvedValue({ success: true, status: 'updated' });

		render(ProjectQuotaForm, {
			quotas: sampleQuotas,
			projectId: 'proj-123',
			onSaveSection,
		});

		const snapInput = screen.getByTestId('quota-volume-snapshots');
		await fireEvent.input(snapInput, { target: { value: '12' } });

		const volumeSaveBtn = screen.getByTestId('save-volume-btn');
		await fireEvent.click(volumeSaveBtn);

		expect(onSaveSection).toHaveBeenCalledTimes(1);
		expect(onSaveSection).toHaveBeenCalledWith('volume', {
			snapshots: 12,
		});
		expect(onSaveSection.mock.calls[0][1]).not.toHaveProperty('volumes');
		expect(onSaveSection.mock.calls[0][1]).not.toHaveProperty('gigabytes');
	});

	it('preserves user drafts on save failure or partial status without false success', async () => {
		const onSaveSection = vi.fn().mockResolvedValue({
			success: false,
			status: 'partial',
			errors: { network: 'Neutron quota limit exceeded policy maximum' },
		});

		render(ProjectQuotaForm, {
			quotas: sampleQuotas,
			projectId: 'proj-123',
			onSaveSection,
		});

		const sgInput = screen.getByTestId('quota-network-security_group') as HTMLInputElement;
		await fireEvent.input(sgInput, { target: { value: '9999' } });

		const networkSaveBtn = screen.getByTestId('save-network-btn');
		await fireEvent.click(networkSaveBtn);

		// Error message is displayed in section
		await vi.waitFor(() => expect(screen.getByText('Neutron quota limit exceeded policy maximum')).not.toBeNull());
		// Success message must NOT be displayed
		expect(screen.queryByText(/저장되었습니다/)).toBeNull();
		// Draft value 9999 is retained!
		expect(sgInput.value).toBe('9999');
	});

	it('keeps the draft and shows a reload warning when the write succeeded but refetch failed', async () => {
		const onSaveSection = vi.fn().mockResolvedValue({
			success: true,
			status: 'updated',
			refreshed: false,
			refreshError: '쿼터를 다시 불러올 수 없습니다. 다시 시도해주세요.',
		});
		render(ProjectQuotaForm, { quotas: sampleQuotas, projectId: 'proj-123', onSaveSection });
		const input = screen.getByTestId('quota-volume-snapshots') as HTMLInputElement;
		await fireEvent.input(input, { target: { value: '40' } });
		await fireEvent.click(screen.getByTestId('save-volume-btn'));

		await vi.waitFor(() => expect(screen.getByRole('alert')).not.toBeNull());
		expect(screen.getByText('쿼터를 다시 불러올 수 없습니다. 다시 시도해주세요.')).not.toBeNull();
		expect(input.value).toBe('40');
		expect(screen.queryByText(/저장되었습니다/)).toBeNull();
	});

	it('retains the edited Cinder snapshot limit when PUT rejects', async () => {
		const onSaveSection = vi.fn().mockRejectedValue(new Error('Cinder update failed'));
		render(ProjectQuotaForm, { quotas: sampleQuotas, projectId: 'proj-123', onSaveSection });
		const input = screen.getByTestId('quota-volume-snapshots') as HTMLInputElement;
		await fireEvent.input(input, { target: { value: '40' } });
		await fireEvent.click(screen.getByTestId('save-volume-btn'));
		await vi.waitFor(() => expect(screen.getByText('Cinder update failed')).not.toBeNull());
		expect(input.value).toBe('40');
		expect(screen.queryByText(/저장되었습니다/)).toBeNull();
	});

	it('취소 (Reset) button reverts section drafts back to baseline', async () => {
		render(ProjectQuotaForm, {
			quotas: sampleQuotas,
			projectId: 'proj-123',
			onSaveSection: unusedSave,
		});

		const coresInput = screen.getByTestId('quota-compute-cores') as HTMLInputElement;
		expect(coresInput.value).toBe('20');

		await fireEvent.input(coresInput, { target: { value: '32' } });
		expect(coresInput.value).toBe('32');
		expect(screen.getByText('수정됨')).not.toBeNull();

		const cancelBtn = screen.getByRole('button', { name: '취소' });
		await fireEvent.click(cancelBtn);

		expect(coresInput.value).toBe('20');
		expect(screen.queryByText('수정됨')).toBeNull();
	});

	it('blocks save and displays validation error when entering values less than -1', async () => {
		const onSaveSection = vi.fn();

		render(ProjectQuotaForm, {
			quotas: sampleQuotas,
			projectId: 'proj-123',
			onSaveSection,
		});

		const coresInput = screen.getByTestId('quota-compute-cores');
		await fireEvent.input(coresInput, { target: { value: '-5' } });

		const saveBtn = screen.getByTestId('save-compute-btn');
		await fireEvent.click(saveBtn);

		expect(screen.getByText(/CPU 코어: -1\(무제한\) 또는 0 이상의 정수를 입력해주세요/)).not.toBeNull();
		expect(onSaveSection).not.toHaveBeenCalled();
	});
});
