<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import OrphanCleanupModal from '$lib/components/admin/orphans/OrphanCleanupModal.svelte';
	import OrphanFipSection from '$lib/components/admin/orphans/OrphanFipSection.svelte';
	import OrphanVolumeSection from '$lib/components/admin/orphans/OrphanVolumeSection.svelte';
	import OrphanShareSection from '$lib/components/admin/orphans/OrphanShareSection.svelte';
	import OrphanSecurityGroupSection from '$lib/components/admin/orphans/OrphanSecurityGroupSection.svelte';
	import { pruneSelection, removeFromSelection } from '$lib/utils/selectionSet';
	import type {
		OrphanFipInfo,
		OrphanVolumeInfo,
		OrphanShareInfo,
		OrphanSecurityGroupInfo,
		OrphanScanResponse,
		CleanupResult,
		OrphanKind,
	} from '$lib/types/orphan';

	type Kind = OrphanKind;

	let fips = $state<OrphanFipInfo[]>([]);
	let volumes = $state<OrphanVolumeInfo[]>([]);
	let shares = $state<OrphanShareInfo[]>([]);
	let secgroups = $state<OrphanSecurityGroupInfo[]>([]);
	let loading = $state(true);
	let scanError = $state('');
	let minAgeDays = $state(14);

	let selectedFips = $state(new Set<string>());
	let selectedVolumes = $state(new Set<string>());
	let selectedShares = $state(new Set<string>());
	let selectedSGs = $state(new Set<string>());

	let confirmKind = $state<Kind | null>(null);
	let confirmIds = $state<string[]>([]);
	let cleaning = $state(false);
	let cleanupError = $state('');
	let cleanupResult = $state<CleanupResult | null>(null);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	const SELECTION_GETTERS: Record<Kind, () => Set<string>> = {
		floating_ip: () => selectedFips,
		volume: () => selectedVolumes,
		manila_share: () => selectedShares,
		security_group: () => selectedSGs,
	};
	const SELECTION_SETTERS: Record<Kind, (v: Set<string>) => void> = {
		floating_ip: (v) => (selectedFips = v),
		volume: (v) => (selectedVolumes = v),
		manila_share: (v) => (selectedShares = v),
		security_group: (v) => (selectedSGs = v),
	};

	async function load() {
		loading = true;
		scanError = '';
		try {
			const data = await api.get<OrphanScanResponse>(
				`/api/v1/admin/orphans?min_age_days=${minAgeDays}`,
				token,
				projectId
			);
			fips = data.floating_ips;
			volumes = data.volumes;
			shares = data.manila_shares ?? [];
			secgroups = data.security_groups ?? [];
			selectedFips = pruneSelection(selectedFips, fips);
			selectedVolumes = pruneSelection(selectedVolumes, volumes);
			selectedShares = pruneSelection(selectedShares, shares);
			selectedSGs = pruneSelection(selectedSGs, secgroups);
		} catch (e) {
			scanError = e instanceof ApiError ? e.message : '스캔 실패';
			fips = [];
			volumes = [];
			shares = [];
			secgroups = [];
		} finally {
			loading = false;
		}
	}

	function openConfirm(kind: Kind) {
		const ids = [...SELECTION_GETTERS[kind]()];
		if (ids.length === 0) return;
		confirmKind = kind;
		confirmIds = ids;
		cleanupError = '';
		cleanupResult = null;
	}

	async function runCleanup() {
		if (!confirmKind || confirmIds.length === 0) return;
		cleaning = true;
		cleanupError = '';
		try {
			const res = await api.post<CleanupResult>(
				'/api/v1/admin/orphans/cleanup',
				{ kind: confirmKind, ids: confirmIds },
				token,
				projectId
			);
			cleanupResult = res;
			SELECTION_SETTERS[confirmKind](
				removeFromSelection(SELECTION_GETTERS[confirmKind](), res.deleted)
			);
			await load();
		} catch (e) {
			cleanupError = e instanceof ApiError ? e.message : '정리 실패';
		} finally {
			cleaning = false;
		}
	}

	function closeConfirm() {
		confirmKind = null;
		confirmIds = [];
		cleanupError = '';
		cleanupResult = null;
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-orphans',
		invokeOnMount: false,
		defaultActive: false,
		defaultInterval: 60,
		intervalOptions: [30, 60, 120]
	});

	onMount(load);
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<PageHeader breadcrumb="시스템 / 고아 리소스" title="고아 리소스 정리">
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading}
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>

	<div class="bg-surface-base border border-line rounded-xl p-4 mb-6 flex flex-wrap items-center gap-4 text-sm">
		<div class="flex items-center gap-2">
			<label for="min-age" class="text-ink-2 text-xs uppercase tracking-wide">Volume 최소 연령(일)</label>
			<input
				id="min-age"
				type="number"
				min="1"
				max="365"
				bind:value={minAgeDays}
				onchange={load}
				class="w-20 bg-surface-sunken border border-line-2 rounded-lg px-2 py-1 text-ink-0 text-sm focus:outline-none"
			/>
		</div>
		<div class="text-xs text-ink-3">
			Floating IP는 분리된 즉시 후보. Volume은 status=available + attachments=[] + 연령 ≥ 임계치.
		</div>
	</div>

	{#if scanError}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">
			{scanError}
		</div>
	{/if}

	{#if loading}
		<div class="text-ink-3 text-sm">로딩 중...</div>
	{:else}
		<OrphanFipSection items={fips} bind:selected={selectedFips} onCleanup={() => openConfirm('floating_ip')} />
		<OrphanVolumeSection items={volumes} bind:selected={selectedVolumes} {minAgeDays} onCleanup={() => openConfirm('volume')} />
		<OrphanShareSection items={shares} bind:selected={selectedShares} onCleanup={() => openConfirm('manila_share')} />
		<OrphanSecurityGroupSection items={secgroups} bind:selected={selectedSGs} onCleanup={() => openConfirm('security_group')} />
	{/if}
</div>

<OrphanCleanupModal
	kind={confirmKind}
	ids={confirmIds}
	{cleaning}
	{cleanupError}
	{cleanupResult}
	onConfirm={runCleanup}
	onClose={closeConfirm}
/>
