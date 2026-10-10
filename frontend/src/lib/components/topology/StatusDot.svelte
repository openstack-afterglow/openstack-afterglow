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
	// 토폴로지 리소스 상태 점. 색은 상태 토큰, 전이 중(warning)일 때만 status-pulse 로 숨쉰다.
	// 장식이므로 aria-hidden — 상태 글자는 옆에서 따로 보여준다.
	interface Props {
		status: string;
		/** false 면 숨쉬지 않는다(범례처럼 실제 상태가 아닌 표본) */
		live?: boolean;
	}

	let { status, live = true }: Props = $props();
	const tone = $derived(statusDotTone(status));
</script>

<span class="status-dot" data-tone={tone} class:is-live={live && tone === 'warning'} aria-hidden="true"></span>

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
	/* reduced-motion 이면 기본 모양(꽉 찬 점)에 멈춘다 */
	.is-live { animation: motion-breathe var(--motion-duration-status-pulse) var(--motion-ease-in-out) infinite; }
</style>
