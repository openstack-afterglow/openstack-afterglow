<script lang="ts">
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { useFileStorageDetailController } from '$lib/stores/fileStorageDetailController.svelte';
	import { formatIsoDateTime } from '$lib/utils/format';

	const s = useFileStorageDetailController();

	const fs = $derived(s.fileStorage!);

	// progress를 퍼센트 숫자로 파싱 (예: "100%" → 100, null → null)
	const progressPct = $derived(() => {
		if (!fs.progress) return null;
		const m = fs.progress.match(/^(\d+(?:\.\d+)?)%$/);
		return m ? parseFloat(m[1]) : null;
	});

	const creatorLabel = $derived(fs.user_name ?? fs.user_id ?? '-');
</script>

<div class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-3">기본 정보</h3>
	<dl class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-x-6 gap-y-2.5">

		<!-- ID -->
		<div class="col-span-full">
			<dt class="text-xs text-ink-3 mb-0.5">ID</dt>
			<dd class="text-sm text-ink-2 font-mono break-all">{fs.id}</dd>
		</div>

		<!-- 상태 + access_rules_status -->
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">상태</dt>
			<dd class="flex items-center gap-1.5 flex-wrap">
				<StatusChip status={fs.status} />
				{#if fs.access_rules_status}
					<StatusChip status={fs.access_rules_status} class="text-[10px]" />
					<span class="text-[10px] text-ink-3">접근 규칙</span>
				{/if}
			</dd>
		</div>

		<!-- 크기 -->
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">크기</dt>
			<dd class="text-sm text-ink-2">{fs.size} GB</dd>
		</div>

		<!-- progress (creating 중이거나 100% 미만인 경우 진행바 포함) -->
		{#if fs.progress}
			<div class="col-span-full">
				<dt class="text-xs text-ink-3 mb-0.5">진행도</dt>
				<dd class="flex items-center gap-2">
					<span class="text-sm text-ink-2">{fs.progress}</span>
					{#if progressPct() !== null && progressPct()! < 100}
						<div class="flex-1 max-w-[160px] h-1.5 bg-surface-sunken rounded-full overflow-hidden">
							<div
								class="h-full rounded-full bg-yellow-500 transition-all"
								style="width: {progressPct()}%"
							></div>
						</div>
					{/if}
				</dd>
			</div>
		{/if}

		<!-- 프로토콜 -->
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">프로토콜</dt>
			<dd>
				<span class="text-xs px-1.5 py-0.5 rounded bg-purple-900/40 text-purple-300">{fs.share_proto}</span>
			</dd>
		</div>

		<!-- 생성 일시 -->
		{#if fs.created_at}
			<div>
				<dt class="text-xs text-ink-3 mb-0.5">생성 일시</dt>
				<dd class="text-sm text-ink-2">{formatIsoDateTime(fs.created_at)}</dd>
			</div>
		{/if}

		<!-- 생성자 -->
		<div>
			<dt class="text-xs text-ink-3 mb-0.5">생성자</dt>
			<dd class="text-sm text-ink-2 font-mono truncate" title={fs.user_id ?? undefined}>{creatorLabel}</dd>
		</div>

		<!-- Share Type -->
		{#if fs.share_type_name}
			<div>
				<dt class="text-xs text-ink-3 mb-0.5">Share 타입</dt>
				<dd class="text-sm text-ink-2 font-mono">{fs.share_type_name}</dd>
			</div>
		{/if}

		<!-- Share Network -->
		{#if fs.share_network_id}
			<div>
				<dt class="text-xs text-ink-3 mb-0.5">Share 네트워크</dt>
				<dd class="text-sm text-ink-2 font-mono truncate">{fs.share_network_id}</dd>
			</div>
		{/if}

		<!-- 라이브러리 정보 -->
		{#if fs.library_name}
			<div>
				<dt class="text-xs text-ink-3 mb-0.5">라이브러리</dt>
				<dd class="text-sm text-ink-2">{fs.library_name}</dd>
			</div>
			<div>
				<dt class="text-xs text-ink-3 mb-0.5">버전</dt>
				<dd class="text-sm text-ink-2">{fs.library_version ?? '-'}</dd>
			</div>
			{#if fs.built_at}
				<div class="col-span-full">
					<dt class="text-xs text-ink-3 mb-0.5">빌드 일시</dt>
					<dd class="text-sm text-ink-2">{fs.built_at}</dd>
				</div>
			{/if}
		{/if}

	</dl>
</div>
