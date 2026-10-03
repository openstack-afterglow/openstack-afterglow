<script lang="ts">
	import type { Volume } from '$lib/types/volume';

	let {
		volume,
		onclose,
		onRename,
		onBoot,
		onExtend,
		onBackup,
		onSnapshot,
		onTransfer,
		onForceDelete,
		onDelete,
		volumeSnapshotsEnabled = true,
		isSystemAdmin = false,
		deleting = false,
		selectionDisabled = false,
	}: {
		volume: Volume;
		onclose: () => void;
		onRename: (volume: Volume) => void;
		onBoot: (volume: Volume) => void;
		onExtend: (volume: Volume) => void;
		onBackup: (volume: Volume) => void;
		onSnapshot: (volume: Volume) => void;
		onTransfer: (volume: Volume) => void;
		onForceDelete: (volume: Volume) => void;
		onDelete: (volume: Volume) => void;
		volumeSnapshotsEnabled?: boolean;
		isSystemAdmin?: boolean;
		deleting?: boolean;
		selectionDisabled?: boolean;
	} = $props();

	const itemClass = 'w-full text-left px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 hover:bg-surface-sunken transition-colors flex items-center gap-2';
	const dangerClass = 'w-full text-left px-3 py-1.5 text-[13px] text-state-danger-text hover:bg-surface-sunken disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2';
	function run(action: (volume: Volume) => void) {
		onclose();
		action(volume);
	}
</script>

<button onclick={() => run(onRename)} class={itemClass}>
	<svg class="w-3.5 h-3.5 text-warm-text" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536M9 13l6.232-6.232a2.5 2.5 0 113.536 3.536L12.536 16.536 8 18l1.464-4.536z" /></svg>
	이름 변경
</button>
{#if volume.status === 'available' && volume.bootable}
	<button onclick={() => run(onBoot)} class={itemClass}>
		<svg class="w-3.5 h-3.5 text-state-success" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3l14 9-14 9V3z" /></svg>
		이 볼륨으로 VM 부팅
	</button>
{/if}
{#if volume.status === 'available' || volume.status === 'in-use'}
	<button onclick={() => run(onExtend)} class={itemClass}>
		<svg class="w-3.5 h-3.5 text-state-info" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" /></svg>
		용량 확장
	</button>
{/if}
{#if volumeSnapshotsEnabled}
	<button onclick={() => run(onSnapshot)} class={itemClass}>
		<svg class="w-3.5 h-3.5 text-warm-text" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
		스냅샷 생성
	</button>
{/if}
{#if volume.status === 'available' || volume.status === 'in-use'}
	<button onclick={() => run(onBackup)} class={itemClass}>
		<svg class="w-3.5 h-3.5 text-state-success" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" /></svg>
		백업 생성
	</button>
{/if}
{#if volume.status === 'available'}
	<button onclick={() => run(onTransfer)} class={itemClass}>
		<svg class="w-3.5 h-3.5 text-state-info" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg>
		이전
	</button>
{/if}
<div class="border-t border-line my-1"></div>
{#if isSystemAdmin && (volume.status === 'error' || volume.status === 'error_deleting' || volume.status === 'deleting')}
	<button onclick={() => run(onForceDelete)} disabled={deleting || selectionDisabled} class={dangerClass}>
		<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
		{deleting ? '삭제 중...' : '강제 삭제'}
	</button>
{/if}
<button
	onclick={() => run(onDelete)}
	disabled={deleting || selectionDisabled || volume.attachments.length > 0}
	title={selectionDisabled ? '일괄 작업이 진행 중입니다' : volume.attachments.length > 0 ? '연결된 볼륨은 삭제할 수 없습니다' : ''}
	class={dangerClass}
>
	<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
	{deleting ? '삭제 중...' : '삭제'}
</button>
