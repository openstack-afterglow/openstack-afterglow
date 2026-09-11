<script lang="ts">
	interface Props {
		title: string;
		description?: string;
		accountHref?: string;
	}

	let {
		title,
		description = '계정 설정에서 이 베타 기능을 켜면 사용할 수 있습니다.',
		accountHref = '/dashboard/account',
	}: Props = $props();
</script>

<div class="beta-gate rounded-lg p-8 text-center shadow-[var(--shadow-restraint)]">
	<div class="beta-gate-icon mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full">
		<span class="text-xl font-semibold">β</span>
	</div>
	<h1 class="text-xl font-semibold">{title}</h1>
	<p class="beta-gate-description mx-auto mt-3 max-w-xl text-sm leading-6">{description}</p>
	<a
		href={accountHref}
		class="beta-gate-link mt-6 inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-offset-2"
	>
		베타 설정으로 이동
	</a>
</div>

<style>
	.beta-gate {
		border: 1px solid color-mix(in oklab, var(--color-warm) 32%, var(--color-line));
		background: color-mix(in oklab, var(--color-warm) 9%, var(--color-surface-raised));
		box-shadow: 0 24px 80px color-mix(in oklab, var(--color-surface-canvas) 42%, transparent);
		color: var(--color-ink-0);
	}

	.beta-gate-icon {
		background: color-mix(in oklab, var(--color-warm) 14%, transparent);
		color: var(--color-warm);
	}

	.beta-gate-description {
		color: var(--color-ink-2);
	}

	.beta-gate-link {
		background: var(--color-warm);
		color: var(--color-surface-canvas);
		--tw-ring-color: color-mix(in oklab, var(--color-warm) 45%, transparent);
		--tw-ring-offset-color: var(--color-surface-canvas);
	}

	.beta-gate-link:hover {
		background: color-mix(in oklab, var(--color-warm) 86%, white);
	}
</style>
