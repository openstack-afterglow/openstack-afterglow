<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { t } from '$lib/i18n/ns/admin-system';
	import RichText from '$lib/i18n/RichText.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { auth } from '$lib/stores/auth';
	import { authDisplayContext } from '$lib/stores/authDisplayContext';
	import { siteConfig } from '$lib/config/site';
	import { api, ApiError, fetchWithAuth } from '$lib/api/client';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import NotionTargetAddForm from '$lib/components/admin/notion/NotionTargetAddForm.svelte';
	import NotionTargetEditForm from '$lib/components/admin/notion/NotionTargetEditForm.svelte';
	import NotionTargetCard from '$lib/components/admin/notion/NotionTargetCard.svelte';
	import type { NotionTarget } from '$lib/components/admin/notion/NotionTargetCard.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { Alert, Button, Card } from '$lib/components/ui';
	import { toast } from '$lib/stores/toast';

	let previousApiBase: string | undefined;
	let backendRevision = 0;
	const backendEpoch = derived(siteConfig, ({ runtime }) => {
		// Observe same-tick A → B → A backend transitions, not only the final URL.
		if (runtime.api_base !== previousApiBase) {
			previousApiBase = runtime.api_base;
			backendRevision += 1;
		}
		return backendRevision;
	});
	const loadContext = $derived(JSON.stringify([$authDisplayContext.key, $backendEpoch]));
	interface RuntimeSetting {
		key: 'notion.sync_enabled';
		value: boolean | null;
		state?: 'configured' | 'missing' | 'unavailable';
	}

	interface RuntimeResponse {
		settings: RuntimeSetting[];
		errors: Array<{ service: 'drover' | 'waygate'; status: number }>;
	}

	let targets = $state<NotionTarget[]>([]);
	let notionSyncEnabled = $state<boolean | null>(null);
	let gateReadAvailable = $state(false);
	let valuesOwner = $state('');
	let generation = 0;
	let loadSequence = 0;
	let gateWriteRevision = 0;
	const gateAvailable = $derived(gateReadAvailable && valuesOwner === loadContext && $authDisplayContext.ready);
	let savingGlobalGate = $state(false);
	let loading = $state(true);
	let targetsLoaded = $state(false);
	let targetsError = $state('');
	let runtimeError = $state('');
	let error = $state('');
	let showAddForm = $state(false);
	let editingTarget = $state<NotionTarget | null>(null);
	let testingId = $state<number | null>(null);
	let testMessages = $state<Record<number, string>>({});
	let testErrors = $state<Record<number, string>>({});

	function requestCurrent(epoch: number, owner: string): boolean {
		return epoch === generation && owner === loadContext && $authDisplayContext.ready;
	}

	function loadError(cause: unknown): string {
		return cause instanceof ApiError
			? t('notion.page.loadFailed', { status: cause.status })
			: t('notion.page.serverError');
	}

	async function fetchTargets() {
		if (!$authDisplayContext.ready) return;
		const requestGeneration = generation;
		const requestSequence = ++loadSequence;
		const requestGateRevision = gateWriteRevision;
		const requestOwner = loadContext;
		const requestToken = $auth.token ?? undefined;
		const requestProject = $auth.projectId ?? undefined;
		const readCurrent = () => requestCurrent(requestGeneration, requestOwner) && requestSequence === loadSequence;
		loading = true;
		targetsLoaded = false;
		targets = [];
		notionSyncEnabled = null;
		gateReadAvailable = false;
		valuesOwner = '';
		error = '';
		targetsError = '';
		runtimeError = '';
		await Promise.allSettled([
			api.get<NotionTarget[]>('/api/v1/admin/notion/targets', requestToken, requestProject, { cache: 'no-store' })
				.then((loadedTargets) => {
					if (!readCurrent()) return;
					targets = loadedTargets;
					targetsLoaded = true;
				})
				.catch((cause) => {
					if (readCurrent()) targetsError = loadError(cause);
				})
				.finally(() => {
					if (readCurrent()) loading = false;
				}),
			api.get<RuntimeResponse>('/api/v1/admin/runtime-settings', requestToken, requestProject, { cache: 'no-store' })
				.then((runtimeSettings) => {
					if (!readCurrent() || requestGateRevision !== gateWriteRevision) return;
					const notionSetting = runtimeSettings.settings.find((setting) => setting.key === 'notion.sync_enabled');
					notionSyncEnabled = notionSetting?.value ?? null;
					gateReadAvailable = notionSetting !== undefined && notionSetting.state !== 'unavailable';
					valuesOwner = requestOwner;
				})
				.catch((cause) => {
					if (readCurrent() && requestGateRevision === gateWriteRevision) runtimeError = loadError(cause);
				})
		]);
	}

	async function setGlobalGate(enabled: boolean) {
		if (!gateAvailable || savingGlobalGate) return;
		const requestGeneration = generation;
		const requestOwner = loadContext;
		const requestToken = $auth.token ?? undefined;
		const requestProject = $auth.projectId ?? undefined;
		savingGlobalGate = true;
		error = '';
		try {
			await api.put(
				'/api/v1/admin/runtime-settings/notion.sync_enabled',
				{ value: enabled },
				requestToken,
				requestProject
			);
			if (requestCurrent(requestGeneration, requestOwner)) {
				++gateWriteRevision;
				notionSyncEnabled = enabled;
				gateReadAvailable = true;
				valuesOwner = requestOwner;
				runtimeError = '';
			}
		} catch (cause) {
			if (!requestCurrent(requestGeneration, requestOwner)) return;
			error = cause instanceof ApiError
				? t('notion.gate.saveFailedDetail', { message: `HTTP ${cause.status}` })
				: t('notion.gate.saveFailed');
		} finally {
			if (requestCurrent(requestGeneration, requestOwner)) savingGlobalGate = false;
		}
	}

	async function deleteTarget(id: number) {
		const requestGeneration = generation;
		const requestOwner = loadContext;
		const requestToken = $auth.token ?? undefined;
		const requestProject = $auth.projectId ?? undefined;
		if (!await confirmDialog(t('notion.delete.confirm'))) return;
		if (!requestCurrent(requestGeneration, requestOwner)) return;
		try {
			await api.delete(
				`/api/v1/admin/notion/targets/${id}`,
				requestToken,
				requestProject
			);
			if (requestCurrent(requestGeneration, requestOwner)) await fetchTargets();
		} catch {
			if (requestCurrent(requestGeneration, requestOwner)) toast.error(t('notion.delete.failed'));
		}
	}

	async function testTarget(id: number) {
		if (!$authDisplayContext.ready) return;
		const requestGeneration = generation;
		const requestOwner = loadContext;
		const requestToken = $auth.token ?? undefined;
		const requestProject = $auth.projectId ?? undefined;
		testingId = id;
		testMessages = { ...testMessages, [id]: '' };
		testErrors = { ...testErrors, [id]: '' };
		try {
			const resp = await fetchWithAuth(`/api/v1/admin/notion/targets/${id}/test`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: '{}',
				signal: AbortSignal.timeout(120_000),
			}, requestToken, requestProject);
			if (!resp.ok) {
				throw new ApiError(resp.status, t('notion.sync.failed'));
			}
			const result = await resp.json();
			if (!requestCurrent(requestGeneration, requestOwner)) return;
			testMessages = { ...testMessages, [id]: result.message };
			testingId = null;
			await fetchTargets();
		} catch (e) {
			if (!requestCurrent(requestGeneration, requestOwner)) return;
			testErrors = {
				...testErrors,
				[id]: e instanceof ApiError
					? `${t('notion.sync.failed')} (${e.status})`
					: (e instanceof Error && e.name === 'TimeoutError')
						? t('notion.sync.timeout')
						: t('notion.sync.failed'),
			};
		} finally {
			if (requestCurrent(requestGeneration, requestOwner)) testingId = null;
		}
	}

	$effect(() => {
		loadContext;
		const ready = $authDisplayContext.ready;
		untrack(() => {
			++generation;
			targets = [];
			targetsLoaded = false;
			notionSyncEnabled = null;
			gateReadAvailable = false;
			valuesOwner = '';
			savingGlobalGate = false;
			showAddForm = false;
			editingTarget = null;
			testingId = null;
			testMessages = {};
			testErrors = {};
			error = '';
			targetsError = '';
			runtimeError = '';
			loading = ready;
			if (ready) void fetchTargets();
		});
		return () => { ++generation; };
	});
</script>

{#snippet integrations(text: string)}<a href="https://www.notion.so/profile/integrations" target="_blank" class="text-warm-text hover:text-warm-text-hover">{text}</a>{/snippet}

<PageShell>
	<PageHeader breadcrumb={t('notion.page.breadcrumb')} title={t('notion.page.title')} subtitle={t('notion.page.subtitle')}>
		{#snippet actions()}
			<button
				onclick={() => { showAddForm = !showAddForm; }}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg transition-colors"
			>
				{showAddForm ? t('notion.actions.cancel') : t('notion.page.addConnection')}
			</button>
		{/snippet}
	</PageHeader>

	{#if error}
		<Alert tone="danger">{error}</Alert>
	{/if}
	{#if targetsError}
		<Alert tone="danger">{targetsError}</Alert>
	{/if}
	{#if runtimeError}
		<Alert tone="danger">{runtimeError}</Alert>
	{/if}

	<Card padding="md" surface="subtle">
		<div class="global-gate">
			<div>
				<p class="gate-eyebrow">{t('notion.gate.eyebrow')}</p>
				<h2>{t('notion.gate.title')}</h2>
				<p>{t('notion.gate.description')}</p>
				{#if gateAvailable && notionSyncEnabled === null}
					<p>{t('policies.state.missing')}</p>
				{/if}
			</div>
			<Button
				variant={notionSyncEnabled ? 'primary' : 'secondary'}
				size="sm"
				disabled={savingGlobalGate || !gateAvailable}
				ariaBusy={savingGlobalGate}
				onclick={() => setGlobalGate(!notionSyncEnabled)}
			>
				{#if savingGlobalGate}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{savingGlobalGate ? t('notion.gate.saving') : !gateAvailable ? t('policies.state.unavailable') : notionSyncEnabled === null ? t('notion.form.enabled') : notionSyncEnabled ? t('notion.gate.enabled') : t('notion.gate.disabled')}
			</Button>
		</div>
	</Card>

	<NotionTargetAddForm bind:open={showAddForm} onAdded={fetchTargets} />

	{#if loading}
		<LoadingState variant="surface" label={t('notion.loadingTargets')} />
	{:else if targetsLoaded && targets.length === 0}
		<div class="bg-surface-base border border-line rounded-lg p-8 text-center">
			<p class="text-ink-2 text-sm">{t('notion.empty.title')}</p>
			<p class="text-ink-2 text-xs mt-1">{t('notion.empty.description')}</p>
		</div>
	{:else}
		<div class="space-y-4">
			{#each targets as target (target.id)}
				<div class="bg-surface-base border border-line rounded-lg p-5">
					{#if editingTarget?.id === target.id}
						<NotionTargetEditForm
							{target}
							onClose={() => (editingTarget = null)}
							onSaved={fetchTargets}
						/>
					{:else}
						<NotionTargetCard
							{target}
							testing={testingId === target.id}
							testMessage={testMessages[target.id] ?? ''}
							testError={testErrors[target.id] ?? ''}
							onTest={() => testTarget(target.id)}
							onEdit={() => (editingTarget = target)}
							onDelete={() => deleteTarget(target.id)}
						/>
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	<div class="mt-6 bg-surface-base border border-line rounded-lg p-5">
		<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-2">{t('notion.setup.title')}</h3>
		<ol class="text-xs text-ink-2 space-y-1.5 list-decimal list-inside">
			<li>
				<RichText segments={t.rich('notion.setup.createIntegration')} tags={{ integrations }} />
			</li>
			<li>{t('notion.setup.createDatabase')}</li>
			<li>{t('notion.setup.copyId')}</li>
			<li>{t('notion.setup.register')}</li>
			<li>{t('notion.setup.multipleTargets')}</li>
		</ol>
	</div>
</PageShell>

<style>
	.global-gate {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
	}

	.gate-eyebrow {
		margin: 0 0 0.25rem;
		color: var(--admin-tone, var(--color-warm));
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.16em;
		text-transform: uppercase;
	}

	h2 {
		margin: 0;
		color: var(--color-ink-0);
		font-size: 1rem;
	}

	.global-gate p:not(.gate-eyebrow) {
		margin: 0.35rem 0 0;
		color: var(--color-ink-2);
		font-size: 0.82rem;
		line-height: 1.5;
	}

	@media (max-width: 640px) {
		.global-gate {
			align-items: flex-start;
			flex-direction: column;
		}
	}
</style>
