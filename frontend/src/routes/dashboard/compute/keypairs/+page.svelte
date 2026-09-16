<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import type { Keypair } from '$lib/types/keypair';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import { Alert, Button, PageHeader, PageShell, ResourceToolbar } from '$lib/components/ui';
  import KeypairCreateModal from '$lib/components/keypair/KeypairCreateModal.svelte';
  import KeypairListTable from '$lib/components/keypair/KeypairListTable.svelte';
  import KeypairEmptyState from '$lib/components/keypair/KeypairEmptyState.svelte';
  import { toast } from '$lib/stores/toast';

  let keypairs = $state<Keypair[]>([]);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let deleting = $state<string | null>(null);
  let copiedFingerprint = $state<string | null>(null);
  let showModal = $state(false);

  async function fetchKeypairs(opts?: { refresh?: boolean }) {
    try {
      keypairs = await api.get<Keypair[]>('/api/v1/keypairs', $auth.token ?? undefined, $auth.projectId ?? undefined, opts);
      error = '';
    } catch (e) {
      error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
    } finally {
      loading = false;
    }
  }

  async function forceRefresh() {
    refreshing = true;
    try {
      await fetchKeypairs({ refresh: true });
    } finally {
      refreshing = false;
    }
  }

  const ar = createAutoRefresh(() => fetchKeypairs(), {
    storageKey: 'dashboard-compute-keypairs',
    invokeOnMount: false,
    defaultActive: true,
    defaultInterval: 60,
    intervalOptions: [10, 15, 30, 60],
  });

  async function createKeypair(form: { name: string; public_key: string }): Promise<{ private_key?: string } | string> {
    try {
      const result = await api.post<Keypair>('/api/v1/keypairs', {
        name: form.name,
        public_key: form.public_key.trim() || null,
      }, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchKeypairs();
      return { private_key: result.private_key };
    } catch (e) {
      return e instanceof ApiError ? e.message : '생성 실패';
    }
  }

  async function deleteKeypair(name: string) {
    if (!await confirmDialog(`키페어 "${name}"을 삭제하시겠습니까?`)) return;
    deleting = name;
    try {
      await api.delete(`/api/v1/keypairs/${name}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchKeypairs();
    } catch (e) {
      toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    } finally {
      deleting = null;
    }
  }

  async function copyFingerprint(fingerprint: string) {
    try {
      await navigator.clipboard.writeText(fingerprint);
      copiedFingerprint = fingerprint;
      setTimeout(() => (copiedFingerprint = null), 2000);
    } catch {
      // 비보안 컨텍스트(HTTP) 또는 권한 거부 시 조용히 무시
    }
  }

  $effect(() => {
    const pid = $auth.projectId;
    if (!pid) return;
    untrack(() => fetchKeypairs());
  });
</script>

<KeypairCreateModal bind:open={showModal} onCreate={createKeypair} />

<PageShell class="space-y-4">
  <PageHeader breadcrumb="COMPUTE / KEYPAIRS" title="키페어">
    {#snippet actions()}
      <Button onclick={() => showModal = true} variant="primary">+ 키페어 생성</Button>
    {/snippet}
  </PageHeader>
  <ResourceToolbar label="키페어 목록 도구">
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={refreshing}
        onManualRefresh={forceRefresh}
      />
    {/snippet}
  </ResourceToolbar>

  {#if error}<Alert tone="danger">{error}</Alert>{/if}

  {#if loading}
    <LoadingSkeleton variant="table" rows={4} />
  {:else if keypairs.length === 0}
    <KeypairEmptyState onCreate={() => (showModal = true)} />
  {:else}
    <KeypairListTable
      {keypairs}
      {deleting}
      {copiedFingerprint}
      onCopy={copyFingerprint}
      onDelete={deleteKeypair}
    />
  {/if}
</PageShell>
