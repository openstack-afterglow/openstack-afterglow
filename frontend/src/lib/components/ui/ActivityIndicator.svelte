<script module lang="ts">
	/**
	 * spinner: generic work · dots: waiting for a reply · orbit: model thinking ·
	 * bars: audio/stream output · pulse: live status · upload/download: transfer direction.
	 */
	export type ActivityVariant = 'spinner' | 'dots' | 'orbit' | 'bars' | 'pulse' | 'upload' | 'download';
	export type ActivityTone = 'accent' | 'warm' | 'ink' | 'success' | 'danger';
	export type ActivitySize = 'xs' | 'sm' | 'md' | 'lg';
</script>

<script lang="ts">
	interface Props {
		variant?: ActivityVariant;
		tone?: ActivityTone;
		size?: ActivitySize;
		/**
		 * Visible status text, announced politely. Omit it only when adjacent visible text already
		 * names the activity; the glyph alone never carries state.
		 */
		label?: string;
		class?: string;
	}

	let { variant = 'spinner', tone = 'accent', size = 'sm', label, class: className = '' }: Props = $props();
</script>

<span
	class="activity activity-{size} {className}"
	data-variant={variant}
	data-tone={tone}
	role={label ? 'status' : undefined}
>
	<span class="glyph" aria-hidden="true">
		{#if variant === 'spinner'}
			<span class="spinner-ring"></span>
		{:else if variant === 'dots'}
			<span class="dot"></span><span class="dot"></span><span class="dot"></span>
		{:else if variant === 'orbit'}
			<span class="orbit-core"></span>
			<span class="orbit-track"><span class="orbit-satellite"></span></span>
			<span class="orbit-track orbit-track-reverse"><span class="orbit-satellite"></span></span>
		{:else if variant === 'bars'}
			<span class="bar"></span><span class="bar"></span><span class="bar"></span><span class="bar"></span>
		{:else if variant === 'pulse'}
			<span class="pulse-ring"></span>
			<span class="pulse-dot"></span>
		{:else}
			<svg class="transfer" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
				<g class="transfer-arrow">
					{#if variant === 'upload'}
						<path d="M8 10.5V3.5M5 6.5l3-3 3 3" />
					{:else}
						<path d="M8 3.5v7M5 7.5l3 3 3-3" />
					{/if}
				</g>
				<path d="M3 11.5v1.25c0 .41.34.75.75.75h8.5c.41 0 .75-.34.75-.75V11.5" />
			</svg>
		{/if}
	</span>
	{#if label}<span class="activity-label">{label}</span>{/if}
</span>

<style>
	.activity {
		--activity-tone: var(--color-accent);
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		min-width: 0;
		vertical-align: middle;
	}
	.activity[data-tone='warm'] { --activity-tone: var(--color-warm); }
	.activity[data-tone='ink'] { --activity-tone: var(--color-ink-2); }
	.activity[data-tone='success'] { --activity-tone: var(--color-state-success); }
	.activity[data-tone='danger'] { --activity-tone: var(--color-state-danger); }
	.activity-xs { --activity-size: 0.75rem; }
	.activity-sm { --activity-size: 1rem; }
	.activity-md { --activity-size: 1.25rem; }
	.activity-lg { --activity-size: 2rem; }

	.glyph {
		position: relative;
		display: inline-flex;
		flex: none;
		align-items: center;
		justify-content: center;
		gap: calc(var(--activity-size) * 0.12);
		width: var(--activity-size);
		height: var(--activity-size);
		color: var(--activity-tone);
	}
	.activity-label {
		min-width: 0;
		color: var(--color-ink-1);
		font-size: 0.75rem;
		line-height: 1.4;
	}
	.activity-md .activity-label { font-size: 0.8125rem; }
	.activity-lg .activity-label { font-size: 0.875rem; }

	.spinner-ring {
		width: 100%;
		height: 100%;
		border: max(1.5px, calc(var(--activity-size) * 0.12)) solid color-mix(in oklab, var(--activity-tone) 22%, transparent);
		border-top-color: var(--activity-tone);
		border-radius: 50%;
		animation: motion-spin var(--motion-duration-spin) linear infinite;
	}

	.dot {
		width: 22%;
		aspect-ratio: 1;
		border-radius: 50%;
		background: var(--activity-tone);
		animation: motion-breathe var(--motion-duration-status-pulse) var(--motion-ease-in-out) infinite;
	}
	.dot:nth-child(2) { animation-delay: calc(var(--motion-duration-status-pulse) / -6 * 4); }
	.dot:nth-child(3) { animation-delay: calc(var(--motion-duration-status-pulse) / -6 * 2); }

	.orbit-core {
		width: 36%;
		aspect-ratio: 1;
		border-radius: 50%;
		background: var(--activity-tone);
		animation: motion-breathe var(--motion-duration-status-pulse) var(--motion-ease-in-out) infinite;
	}
	.orbit-track {
		position: absolute;
		inset: 0;
		border: 1px solid color-mix(in oklab, var(--activity-tone) 24%, transparent);
		border-radius: 50%;
		animation: motion-spin calc(var(--motion-duration-spin) * 2.5) linear infinite;
	}
	.orbit-track-reverse {
		inset: 18%;
		border-color: transparent;
		animation-direction: reverse;
		animation-duration: calc(var(--motion-duration-spin) * 1.75);
	}
	.orbit-satellite {
		position: absolute;
		top: -2px;
		left: calc(50% - 2px);
		width: 4px;
		height: 4px;
		border-radius: 50%;
		background: var(--activity-tone);
	}
	.orbit-track-reverse .orbit-satellite {
		top: auto;
		bottom: -2px;
		background: var(--color-accent-2);
	}

	.bar {
		width: 16%;
		height: 100%;
		border-radius: 999px;
		background: var(--activity-tone);
		transform-origin: center bottom;
		transform: scaleY(var(--bar-rest, 0.6));
		animation: motion-bars calc(var(--motion-duration-spin) * 1.25) var(--motion-ease-in-out) infinite;
	}
	.bar:nth-child(1) { --bar-rest: 0.45; animation-delay: calc(var(--motion-duration-spin) / -5 * 1); }
	.bar:nth-child(2) { --bar-rest: 0.9; animation-delay: calc(var(--motion-duration-spin) / -5 * 3); }
	.bar:nth-child(3) { --bar-rest: 0.65; animation-delay: calc(var(--motion-duration-spin) / -5 * 2); }
	.bar:nth-child(4) { --bar-rest: 0.8; animation-delay: calc(var(--motion-duration-spin) / -5 * 4); }

	.pulse-dot {
		position: relative;
		width: 45%;
		aspect-ratio: 1;
		border-radius: 50%;
		background: var(--activity-tone);
	}
	.pulse-ring {
		position: absolute;
		left: 27.5%;
		top: 27.5%;
		width: 45%;
		aspect-ratio: 1;
		border-radius: 50%;
		background: var(--activity-tone);
		opacity: 0;
		animation: motion-ripple var(--motion-duration-status-pulse) var(--motion-ease-out) infinite;
	}

	.transfer {
		width: 100%;
		height: 100%;
		overflow: visible;
	}
	.transfer-arrow {
		transform-box: fill-box;
		animation: motion-rise var(--motion-duration-status-pulse) var(--motion-ease-in-out) infinite;
	}
	[data-variant='download'] .transfer-arrow {
		animation-name: motion-sink;
	}
</style>
