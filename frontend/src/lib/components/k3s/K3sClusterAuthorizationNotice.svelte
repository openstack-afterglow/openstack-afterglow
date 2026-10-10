<script lang="ts">
	// Drover's continuous cluster authority (Stampede, reconcile, guest plugins) is a current project
	// user's restricted credential. Legacy clusters have none until a clusters-admin reauthorizes; the
	// notice stays silent while authority is healthy and never handles credential secrets.
	import { t } from '$lib/i18n/ns/drover';
	import { t as tc } from '$lib/i18n/ns/common';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { ApiError } from '$lib/api/client';
	import { getClusterAuthorization, reauthorizeCluster, retireClusterCredentials } from '$lib/api/k3s';
	import { auth } from '$lib/stores/auth';
	import { k3sPermissions } from '$lib/stores/k3sPermissions';
	import { toast } from '$lib/stores/toast';
	import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
	import type { K3sClusterAuthorization } from '$lib/types/k3s';

	const POLL_INTERVAL_MS = 5000;
	// Drover bounds a guest rollout by guest_rollout_timeout_seconds (default 600s).
	const MAX_POLLS = 150;

	const s = useK3sClusterDetailController();

	let status = $state<K3sClusterAuthorization | null>(null);
	let loadError = $state('');
	let actionError = $state('');
	let busy = $state<'reauthorize' | 'retire' | null>(null);
	let scopeGeneration = 0;

	const clusterId = $derived(s.cluster?.id ?? '');
	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const userId = $derived($auth.userId ?? null);
	const enabled = $derived(!s.adminMode && $k3sPermissions.inventory && clusterId !== '' && !!token);
	const isActive = $derived(s.cluster?.status === 'ACTIVE');
	const rolling = $derived((status?.staged_generations?.length ?? 0) > 0);
	const ownRetiring = $derived(
		userId ? (status?.owner_revocation_required ?? []).filter((item) => item.owner_user_id === userId) : [],
	);

	function failureDetail(error: unknown): string {
		return error instanceof ApiError ? error.message : t('detail.serverError');
	}

	async function load(fence: number, signal?: AbortSignal) {
		const id = clusterId;
		try {
			const next = await getClusterAuthorization(id, token, projectId, signal);
			if (fence !== scopeGeneration) return;
			status = next;
			loadError = '';
		} catch (error) {
			if (fence !== scopeGeneration || signal?.aborted) return;
			// Missing inventory authority or a vanished cluster is not this notice's concern.
			if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
				status = null;
				loadError = '';
				return;
			}
			loadError = t('authorization.loadFailed', { status: error instanceof ApiError ? error.status : 0 });
		}
	}

	$effect(() => {
		// Token, project and cluster form the request scope; any change discards late responses.
		void [clusterId, token, projectId];
		const fence = ++scopeGeneration;
		status = null;
		loadError = '';
		actionError = '';
		busy = null;
		if (!enabled) return;
		const controller = new AbortController();
		void load(fence, controller.signal);
		return () => controller.abort();
	});

	$effect(() => {
		if (!enabled || !rolling) return;
		const fence = scopeGeneration;
		let polls = 0;
		const timer = setInterval(() => {
			if (fence !== scopeGeneration || ++polls > MAX_POLLS) {
				clearInterval(timer);
				return;
			}
			if (typeof document === 'undefined' || !document.hidden) void load(fence);
		}, POLL_INTERVAL_MS);
		return () => clearInterval(timer);
	});

	async function reauthorize() {
		if (busy || !$k3sPermissions.administerClusters || !isActive || !clusterId) return;
		const fence = scopeGeneration;
		busy = 'reauthorize';
		actionError = '';
		try {
			const result = await reauthorizeCluster(clusterId, token, projectId);
			if (fence !== scopeGeneration) return;
			toast.success(t('authorization.started', { generation: result.generation }));
			await load(fence);
		} catch (error) {
			if (fence === scopeGeneration) actionError = t('authorization.actionFailed', { detail: failureDetail(error) });
		} finally {
			if (fence === scopeGeneration) busy = null;
		}
	}

	async function retireOwn() {
		if (busy || ownRetiring.length === 0 || !clusterId) return;
		const fence = scopeGeneration;
		busy = 'retire';
		actionError = '';
		try {
			const result = await retireClusterCredentials(clusterId, token, projectId);
			if (fence !== scopeGeneration) return;
			toast.success(t('authorization.retired', { count: result.deleted_credential_ids.length }));
			await load(fence);
		} catch (error) {
			if (fence === scopeGeneration) actionError = t('authorization.actionFailed', { detail: failureDetail(error) });
		} finally {
			if (fence === scopeGeneration) busy = null;
		}
	}
</script>

{#if enabled}
	{#if loadError}
		<Alert tone="warning" class="mb-3">{loadError}</Alert>
	{:else if status && rolling}
		<Alert tone="info" title={t('authorization.inProgressTitle')} class="mb-3">
			<span class="inline-flex items-center gap-2">
				<ActivityIndicator size="xs" label={tc('state.processing')} />
				{t('authorization.inProgressBody')}
			</span>
		</Alert>
	{:else if status && !status.authorized}
		<Alert tone="warning" title={t('authorization.requiredTitle')} class="mb-3">
			<p>{t('authorization.requiredBody')}</p>
			{#if !$k3sPermissions.administerClusters}
				<p class="mt-1">{t('authorization.adminRequired')}</p>
			{:else if !isActive}
				<p class="mt-1">{t('authorization.activeRequired')}</p>
			{/if}
			{#if actionError}<p class="mt-1" role="alert">{actionError}</p>{/if}
			{#snippet actions()}
				{#if $k3sPermissions.administerClusters}
					<Button
						variant="secondary"
						size="sm"
						disabled={busy !== null || !isActive}
						ariaBusy={busy === 'reauthorize'}
						onclick={reauthorize}
					>
						{#if busy === 'reauthorize'}<ActivityIndicator size="xs" label={tc('state.processing')} />{:else}{t('authorization.reauthorize')}{/if}
					</Button>
				{/if}
			{/snippet}
		</Alert>
	{/if}
	{#if status && ownRetiring.length > 0}
		<Alert tone="neutral" title={t('authorization.retireTitle')} class="mb-3">
			<p>{t('authorization.retireBody', { count: ownRetiring.length })}</p>
			{#if actionError && status.authorized}<p class="mt-1" role="alert">{actionError}</p>{/if}
			{#snippet actions()}
				<Button
					variant="subtle"
					size="sm"
					disabled={busy !== null}
					ariaBusy={busy === 'retire'}
					onclick={retireOwn}
				>
					{#if busy === 'retire'}<ActivityIndicator size="xs" label={tc('state.processing')} />{:else}{t('authorization.retire')}{/if}
				</Button>
			{/snippet}
		</Alert>
	{/if}
{/if}
