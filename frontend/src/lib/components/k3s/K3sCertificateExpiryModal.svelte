<script lang="ts">
	import { t } from '$lib/i18n/ns/drover';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { api } from '$lib/api/client';
	import { k3sPermissions } from '$lib/stores/k3sPermissions';
	import type { CertificateExpiryResponse, CertificateInfo } from '$lib/types/k3s';
	import K3sRotateProgressModal from './K3sRotateProgressModal.svelte';

	interface Props {
		clusterId: string;
		clusterName: string;
		masterCount?: number;
		token?: string;
		projectId?: string;
		onclose: () => void;
	}

	const { clusterId, clusterName, masterCount = 1, token, projectId, onclose }: Props = $props();

	let data = $state<CertificateExpiryResponse | null>(null);
	let loading = $state(true);
	let error = $state('');
	let showRotateModal = $state(false);

	$effect(() => {
		void load();
	});

	async function load() {
		loading = true;
		error = '';
		try {
			data = await api.get<CertificateExpiryResponse>(
				`/api/v1/k3s/clusters/${clusterId}/certificate-expiry`,
				token,
				projectId,
			);
		} catch (e) {
			error = e instanceof Error ? e.message : t('certificateExpiry.loadFailed');
		} finally {
			loading = false;
		}
	}

	function expiryColor(days: number): string {
		if (days > 60) return 'text-green-400 bg-green-900/30';
		if (days > 30) return 'text-yellow-400 bg-yellow-900/30';
		return 'text-red-400 bg-red-900/30';
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleDateString(intlLocale(), { year: 'numeric', month: '2-digit', day: '2-digit' });
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onclose();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="fixed inset-0 z-50 flex items-center justify-center">
	<button class="absolute inset-0 bg-surface-scrim/60" onclick={onclose} aria-label={t('certificateExpiry.close')} tabindex="-1"></button>

	<div class="motion-enter relative bg-surface-canvas border border-line rounded-lg w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)] max-h-[85vh] overflow-y-auto">
		<div class="flex items-center justify-between px-5 py-4 border-b border-line">
			<h2 class="text-sm font-semibold text-ink-0">{t('certificateExpiry.title', { name: clusterName })}</h2>
			<button onclick={onclose} class="text-ink-2 hover:text-ink-0 transition-colors text-lg leading-none">&times;</button>
		</div>

		<div class="p-5 space-y-4">
			{#if loading}
				<div class="text-ink-2 text-sm text-center py-6"><ActivityIndicator label={t('certificateExpiry.loading')} /></div>
			{:else if error}
				<p class="text-red-400 text-sm">{error}</p>
			{:else if data}
				{#snippet certRow(label: string, cert: CertificateInfo | null)}
					<div class="bg-surface-base border border-line rounded-xl p-4 space-y-2">
						<div class="flex items-center justify-between">
							<span class="text-xs text-ink-2 uppercase tracking-wide">{label}</span>
							{#if cert}
								<span class="text-xs px-2 py-0.5 rounded-full {expiryColor(cert.days_remaining)}">
									{t('certificateExpiry.daysRemaining', { count: cert.days_remaining })}
								</span>
							{:else}
								<span class="text-xs text-ink-2">{t('certificateExpiry.none')}</span>
							{/if}
						</div>
						{#if cert}
							<dl class="space-y-1 text-xs">
								<div class="flex justify-between gap-2">
									<dt class="text-ink-2 shrink-0">{t('certificateExpiry.expiresAt')}</dt>
									<dd class="text-ink-2 font-mono">{formatDate(cert.not_after)}</dd>
								</div>
								<div class="flex justify-between gap-2">
									<dt class="text-ink-2 shrink-0">{t('certificateExpiry.issuedAt')}</dt>
									<dd class="text-ink-2 font-mono">{formatDate(cert.not_before)}</dd>
								</div>
								<div class="flex justify-between gap-2">
									<dt class="text-ink-2 shrink-0">{t('certificateExpiry.subject')}</dt>
									<dd class="text-ink-2 font-mono truncate max-w-[240px]" title={cert.subject}>{cert.subject}</dd>
								</div>
								<div class="flex justify-between gap-2">
									<dt class="text-ink-2 shrink-0">{t('certificateExpiry.issuer')}</dt>
									<dd class="text-ink-2 font-mono truncate max-w-[240px]" title={cert.issuer}>{cert.issuer}</dd>
								</div>
							</dl>
						{/if}
					</div>
				{/snippet}

				{@render certRow(t('certificateExpiry.ca'), data.ca)}
				{@render certRow(t('certificateExpiry.client'), data.client)}

				{#if data.server_via_tls.length > 0}
					{#each data.server_via_tls as cert, i}
						{@render certRow(t('certificateExpiry.serverTlsNumber', { number: i + 1 }), cert)}
					{/each}
				{:else}
					<div class="bg-surface-base border border-line rounded-xl p-4">
						<span class="text-xs text-ink-2 uppercase tracking-wide">{t('certificateExpiry.serverTls')}</span>
						<p class="text-xs text-ink-2 mt-1">{t('certificateExpiry.probeUnavailable')}</p>
					</div>
				{/if}
			{/if}
		</div>

		<div class="px-5 pb-4 flex justify-end gap-2">
			<button
				onclick={load}
				class="text-xs px-3 py-1.5 rounded-lg bg-surface-sunken hover:bg-surface-selected text-ink-1 transition-colors"
			>
				{t('certificateExpiry.refresh')}
			</button>
			{#if masterCount >= 3 && $k3sPermissions.administerClusters}
				<button
					onclick={() => (showRotateModal = true)}
					class="text-xs px-3 py-1.5 rounded-lg bg-action-warm hover:bg-action-warm-hover text-action-on-warm transition-colors"
					title={t('certificateExpiry.rotateTooltip')}
				>
					{t('certificateExpiry.rotate')}
				</button>
			{/if}
			<button
				onclick={onclose}
				class="text-xs px-3 py-1.5 rounded-lg bg-surface-selected hover:bg-surface-selected text-ink-0 transition-colors"
			>
				{t('certificateExpiry.close')}
			</button>
		</div>
	</div>
</div>

{#if showRotateModal}
	<K3sRotateProgressModal
		{clusterId}
		{clusterName}
		{token}
		{projectId}
		onclose={() => {
			showRotateModal = false;
			void load();
		}}
	/>
{/if}
