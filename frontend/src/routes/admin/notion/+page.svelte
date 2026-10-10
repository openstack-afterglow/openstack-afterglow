<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-system';
	import RichText from '$lib/i18n/RichText.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError, fetchWithAuth } from '$lib/api/client';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import NotionTargetAddForm from '$lib/components/admin/notion/NotionTargetAddForm.svelte';
	import NotionTargetEditForm from '$lib/components/admin/notion/NotionTargetEditForm.svelte';
	import NotionTargetCard from '$lib/components/admin/notion/NotionTargetCard.svelte';
	import type { NotionTarget } from '$lib/components/admin/notion/NotionTargetCard.svelte';
	import { ActivityIndicator, Alert, Button, Card } from '$lib/components/ui';
	import { toast } from '$lib/stores/toast';


	interface RuntimeSetting {
		key: 'notion.sync_enabled';
		value: boolean | null;
	}

	let targets = $state<NotionTarget[]>([]);
	let notionSyncEnabled = $state<boolean | null>(null);
	let savingGlobalGate = $state(false);
	let loading = $state(true);
	let error = $state('');
	let showAddForm = $state(false);
	let editingTarget = $state<NotionTarget | null>(null);
	let testingId = $state<number | null>(null);
	let testMessages = $state<Record<number, string>>({});
	let testErrors = $state<Record<number, string>>({});

	async function fetchTargets() {
		loading = true;
		try {
			const [loadedTargets, runtimeSettings] = await Promise.all([
				api.get<NotionTarget[]>(
					'/api/v1/admin/notion/targets',
					$auth.token ?? undefined,
					$auth.projectId ?? undefined
				),
				api.get<RuntimeSetting[]>(
					'/api/v1/admin/runtime-settings',
					$auth.token ?? undefined,
					$auth.projectId ?? undefined
				)
			]);
			targets = loadedTargets;
			notionSyncEnabled = runtimeSettings.find((setting) => setting.key === 'notion.sync_enabled')?.value ?? false;
		} catch (e) {
			error = e instanceof ApiError ? t('notion.page.loadFailed', { status: e.status }) : t('notion.page.serverError');
		} finally {
			loading = false;
		}
	}

	async function setGlobalGate(enabled: boolean) {
		savingGlobalGate = true;
		try {
			await api.put(
				'/api/v1/admin/runtime-settings/notion.sync_enabled',
				{ value: enabled },
				$auth.token ?? undefined,
				$auth.projectId ?? undefined
			);
			notionSyncEnabled = enabled;
		} catch (cause) {
			error = cause instanceof ApiError ? t('notion.gate.saveFailedDetail', { message: cause.message }) : t('notion.gate.saveFailed');
		} finally {
			savingGlobalGate = false;
		}
	}

	async function deleteTarget(id: number) {
		if (!await confirmDialog(t('notion.delete.confirm'))) return;
		try {
			await api.delete(
				`/api/v1/admin/notion/targets/${id}`,
				$auth.token ?? undefined,
				$auth.projectId ?? undefined
			);
			await fetchTargets();
		} catch {
			toast.error(t('notion.delete.failed'));
		}
	}

	async function testTarget(id: number) {
		testingId = id;
		testMessages = { ...testMessages, [id]: '' };
		testErrors = { ...testErrors, [id]: '' };
		try {
			const resp = await fetchWithAuth(`/api/v1/admin/notion/targets/${id}/test`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: '{}',
				signal: AbortSignal.timeout(120_000),
			}, $auth.token ?? undefined, $auth.projectId ?? undefined);
			if (!resp.ok) {
				const body = await resp.json().catch(() => ({ detail: resp.statusText }));
				throw new ApiError(resp.status, body?.detail || resp.statusText);
			}
			const result = await resp.json();
			testMessages = { ...testMessages, [id]: result.message };
			await fetchTargets();
		} catch (e) {
			testErrors = {
				...testErrors,
				[id]: e instanceof ApiError
					? e.message
					: (e instanceof Error && e.name === 'TimeoutError')
						? t('notion.sync.timeout')
						: t('notion.sync.failed'),
			};
		} finally {
			testingId = null;
		}
	}

	$effect(() => {
		if ($auth.token) fetchTargets();
	});
</script>

{#snippet integrations(text: string)}<a href="https://www.notion.so/profile/integrations" target="_blank" class="text-warm-text hover:text-warm-text-hover">{text}</a>{/snippet}

<div class="p-4 md:p-8 max-w-3xl">
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

	<Card padding="md" surface="subtle">
		<div class="global-gate">
			<div>
				<p class="gate-eyebrow">{t('notion.gate.eyebrow')}</p>
				<h2>{t('notion.gate.title')}</h2>
				<p>{t('notion.gate.description')}</p>
			</div>
			<Button
				variant={notionSyncEnabled ? 'primary' : 'secondary'}
				size="sm"
				disabled={savingGlobalGate || notionSyncEnabled === null}
				ariaBusy={savingGlobalGate}
				onclick={() => setGlobalGate(!notionSyncEnabled)}
			>
				{#if savingGlobalGate}<ActivityIndicator size="xs" tone="ink" />{/if}{savingGlobalGate ? t('notion.gate.saving') : notionSyncEnabled ? t('notion.gate.enabled') : t('notion.gate.disabled')}
			</Button>
		</div>
	</Card>

	<NotionTargetAddForm bind:open={showAddForm} onAdded={fetchTargets} />

	{#if loading}
		<div class="space-y-3" role="status" aria-busy="true" aria-label={t('notion.loadingTargets')}>
			{#each [0, 1] as _}
				<div class="motion-skeleton rounded-lg h-32"></div>
			{/each}
		</div>
	{:else if targets.length === 0}
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
</div>

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
