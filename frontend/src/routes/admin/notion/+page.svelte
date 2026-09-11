<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError, getBaseUrl } from '$lib/api/client';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import NotionTargetAddForm from '$lib/components/admin/notion/NotionTargetAddForm.svelte';
	import NotionTargetEditForm from '$lib/components/admin/notion/NotionTargetEditForm.svelte';
	import NotionTargetCard from '$lib/components/admin/notion/NotionTargetCard.svelte';
	import type { NotionTarget } from '$lib/components/admin/notion/NotionTargetCard.svelte';
	import { Alert, Button, Card } from '$lib/components/ui';
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
			error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
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
			error = cause instanceof ApiError ? `전역 동기화 설정 저장 실패: ${cause.message}` : '전역 동기화 설정 저장 실패';
		} finally {
			savingGlobalGate = false;
		}
	}

	async function deleteTarget(id: number) {
		if (!await confirmDialog('이 연동 대상을 삭제하시겠습니까?')) return;
		try {
			await api.delete(
				`/api/v1/admin/notion/targets/${id}`,
				$auth.token ?? undefined,
				$auth.projectId ?? undefined
			);
			await fetchTargets();
		} catch {
			toast.error('삭제 실패');
		}
	}

	async function testTarget(id: number) {
		testingId = id;
		testMessages = { ...testMessages, [id]: '' };
		testErrors = { ...testErrors, [id]: '' };
		try {
			const headers: Record<string, string> = { 'Content-Type': 'application/json' };
			if ($auth.token) headers['Authorization'] = `Bearer ${$auth.token}`;
			if ($auth.projectId) headers['X-Project-Id'] = $auth.projectId;
			const resp = await fetch(`${getBaseUrl()}/api/v1/admin/notion/targets/${id}/test`, {
				method: 'POST',
				headers,
				body: '{}',
				signal: AbortSignal.timeout(120_000),
			});
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
						? '동기화 시간 초과 (2분)'
						: '테스트 실패',
			};
		} finally {
			testingId = null;
		}
	}

	$effect(() => {
		if ($auth.token) fetchTargets();
	});
</script>

<div class="p-4 md:p-8 max-w-3xl">
	<PageHeader breadcrumb="SYSTEM / NOTION" title="Notion 연동" subtitle="OpenStack 리소스를 여러 Notion DB에 동시에 동기화합니다.">
		{#snippet actions()}
			<button
				onclick={() => { showAddForm = !showAddForm; }}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg transition-colors"
			>
				{showAddForm ? '취소' : '+ 연결 추가'}
			</button>
		{/snippet}
	</PageHeader>

	{#if error}
		<Alert tone="danger">{error}</Alert>
	{/if}

	<Card padding="md" surface="subtle">
		<div class="global-gate">
			<div>
				<p class="gate-eyebrow">Global synchronization gate</p>
				<h2>Notion 전체 동기화</h2>
				<p>비활성화하면 worker와 수동 테스트 모두 외부 Notion·OpenStack 호출 전에 중단합니다. 대상과 자격 증명은 유지됩니다.</p>
			</div>
			<Button
				variant={notionSyncEnabled ? 'primary' : 'secondary'}
				size="sm"
				disabled={savingGlobalGate || notionSyncEnabled === null}
				onclick={() => setGlobalGate(!notionSyncEnabled)}
			>
				{savingGlobalGate ? '저장 중…' : notionSyncEnabled ? '동기화 켜짐' : '동기화 꺼짐'}
			</Button>
		</div>
	</Card>

	<NotionTargetAddForm bind:open={showAddForm} onAdded={fetchTargets} />

	{#if loading}
		<div class="space-y-3">
			{#each [0, 1] as _}
				<div class="animate-pulse bg-surface-base rounded-lg h-32"></div>
			{/each}
		</div>
	{:else if targets.length === 0}
		<div class="bg-surface-base border border-line rounded-lg p-8 text-center">
			<p class="text-ink-3 text-sm">등록된 Notion 연동 대상이 없습니다.</p>
			<p class="text-ink-3 text-xs mt-1">"연결 추가" 버튼을 눌러 시작하세요.</p>
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
		<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-2">설정 방법</h3>
		<ol class="text-xs text-ink-3 space-y-1.5 list-decimal list-inside">
			<li>
				<a href="https://www.notion.so/profile/integrations" target="_blank" class="text-action-warm hover:text-action-warm-hover">Notion Integrations</a>에서 Internal Integration 생성
			</li>
			<li>Notion에서 빈 Database 페이지 생성 후 Integration 연결 추가</li>
			<li>Database URL에서 32자리 ID 복사</li>
			<li>"연결 추가" 버튼으로 등록 — 필요한 컬럼이 자동 생성됩니다</li>
			<li>여러 연동 대상을 등록하면 동일한 데이터를 각 Notion DB에 동시에 동기화합니다</li>
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
