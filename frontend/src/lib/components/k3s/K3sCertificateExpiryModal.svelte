<script lang="ts">
	import { api } from '$lib/api/client';
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
			error = e instanceof Error ? e.message : '조회 실패';
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
		return new Date(iso).toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' });
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onclose();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="fixed inset-0 z-50 flex items-center justify-center">
	<button class="absolute inset-0 bg-surface-scrim/60" onclick={onclose} aria-label="닫기" tabindex="-1"></button>

	<div class="relative bg-surface-canvas border border-line rounded-lg w-full max-w-lg mx-4 shadow-[var(--shadow-restraint)] max-h-[85vh] overflow-y-auto">
		<div class="flex items-center justify-between px-5 py-4 border-b border-line">
			<h2 class="text-sm font-semibold text-ink-0">인증서 만료 — {clusterName}</h2>
			<button onclick={onclose} class="text-ink-3 hover:text-ink-0 transition-colors text-lg leading-none">&times;</button>
		</div>

		<div class="p-5 space-y-4">
			{#if loading}
				<p class="text-ink-2 text-sm text-center py-6">조회 중...</p>
			{:else if error}
				<p class="text-red-400 text-sm">{error}</p>
			{:else if data}
				{#snippet certRow(label: string, cert: CertificateInfo | null)}
					<div class="bg-surface-base border border-line rounded-xl p-4 space-y-2">
						<div class="flex items-center justify-between">
							<span class="text-xs text-ink-2 uppercase tracking-wide">{label}</span>
							{#if cert}
								<span class="text-xs px-2 py-0.5 rounded-full {expiryColor(cert.days_remaining)}">
									{cert.days_remaining}일 남음
								</span>
							{:else}
								<span class="text-xs text-ink-3">없음</span>
							{/if}
						</div>
						{#if cert}
							<dl class="space-y-1 text-xs">
								<div class="flex justify-between gap-2">
									<dt class="text-ink-3 shrink-0">만료일</dt>
									<dd class="text-ink-2 font-mono">{formatDate(cert.not_after)}</dd>
								</div>
								<div class="flex justify-between gap-2">
									<dt class="text-ink-3 shrink-0">발급일</dt>
									<dd class="text-ink-2 font-mono">{formatDate(cert.not_before)}</dd>
								</div>
								<div class="flex justify-between gap-2">
									<dt class="text-ink-3 shrink-0">Subject</dt>
									<dd class="text-ink-2 font-mono truncate max-w-[240px]" title={cert.subject}>{cert.subject}</dd>
								</div>
								<div class="flex justify-between gap-2">
									<dt class="text-ink-3 shrink-0">Issuer</dt>
									<dd class="text-ink-2 font-mono truncate max-w-[240px]" title={cert.issuer}>{cert.issuer}</dd>
								</div>
							</dl>
						{/if}
					</div>
				{/snippet}

				{@render certRow('CA 인증서', data.ca)}
				{@render certRow('클라이언트 인증서', data.client)}

				{#if data.server_via_tls.length > 0}
					{#each data.server_via_tls as cert, i}
						{@render certRow(`서버 TLS ${i + 1}`, cert)}
					{/each}
				{:else}
					<div class="bg-surface-base border border-line rounded-xl p-4">
						<span class="text-xs text-ink-2 uppercase tracking-wide">서버 TLS</span>
						<p class="text-xs text-ink-3 mt-1">TLS 프로브 불가 (API 서버 비접근 또는 타임아웃)</p>
					</div>
				{/if}
			{/if}
		</div>

		<div class="px-5 pb-4 flex justify-end gap-2">
			<button
				onclick={load}
				class="text-xs px-3 py-1.5 rounded-lg bg-surface-sunken hover:bg-surface-selected text-ink-1 transition-colors"
			>
				새로고침
			</button>
			{#if masterCount >= 3}
				<button
					onclick={() => (showRotateModal = true)}
					class="text-xs px-3 py-1.5 rounded-lg bg-action-warm hover:bg-action-warm-hover text-action-on-warm transition-colors"
					title="인증서 rolling 회전 (HA 클러스터 전용)"
				>
					인증서 회전
				</button>
			{/if}
			<button
				onclick={onclose}
				class="text-xs px-3 py-1.5 rounded-lg bg-surface-selected hover:bg-surface-selected text-ink-0 transition-colors"
			>
				닫기
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
