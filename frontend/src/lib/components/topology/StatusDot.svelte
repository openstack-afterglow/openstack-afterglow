<script module lang="ts">
	export type StatusDotTone = 'success' | 'danger' | 'warning';

	/** ACTIVE = 정상, ERROR·SHUTOFF = 장애/정지, 그 밖(BUILD·PENDING_* 등) = 전이 중. */
	export function statusDotTone(status: string): StatusDotTone {
		if (status === 'ACTIVE') return 'success';
		if (status === 'ERROR' || status === 'SHUTOFF') return 'danger';
		return 'warning';
	}
</script>

<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	// 실제 전이 중인 리소스만 공통 작업 표시를 사용한다. 안정 상태와 범례는 점으로 남긴다.
	// 장식이므로 aria-hidden — 상태 글자는 옆에서 따로 보여준다.
	interface Props {
		status: string;
		/** false 면 실제 진행 표시 대신 정적인 범례 점을 표시한다. */
		live?: boolean;
	}

	let { status, live = true }: Props = $props();
	const tone = $derived(statusDotTone(status));
</script>

{#if live && tone === 'warning'}
	<LoadingState variant="control" label="" aria-hidden="true" />
{:else}
	<span class="status-dot" data-tone={tone} aria-hidden="true"></span>
{/if}

<style>
	.status-dot {
		display: inline-block;
		flex-shrink: 0;
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 999px;
		background: var(--color-state-warning);
	}
	.status-dot[data-tone='success'] { background: var(--color-state-success); }
	.status-dot[data-tone='danger'] { background: var(--color-state-danger); }
</style>
