<script lang="ts">
	import { goto } from '$app/navigation';
	import { MOCKUP_COOKIE, MOCKUP_QUERY_KEY, type MockupProfileId } from '$lib/mockup/contracts';
	import { t } from '$lib/i18n/ns/shell';

	import Button from '$lib/components/ui/Button.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';

	let { profile = 'on' }: { profile?: MockupProfileId | null } = $props();

	async function exitTutorialMode() {
		const secure = location.protocol === 'https:' ? '; Secure' : '';
		document.cookie = `${MOCKUP_COOKIE}=; path=/; SameSite=Strict${secure}; max-age=0`;
		await goto(`/?${MOCKUP_QUERY_KEY}=off`, { replaceState: true, invalidateAll: true });
	}
</script>

<div class="mockup-banner" role="status" aria-live="polite">
	<div class="mockup-copy">
		<Pill tone="warning" dot>{profile === 'admin' ? t('mockup.adminPreview') : t('mockup.tutorial')}</Pill>
		<span class="mockup-message">{profile === 'admin' ? t('mockup.adminMessage') : t('mockup.tutorialMessage')}</span>
	</div>
	<div class="mockup-actions">
		<Button variant="outline" size="xs" onclick={exitTutorialMode}>{t('mockup.exit')}</Button>
	</div>
</div>

<style>
	.mockup-banner {
		position: fixed;
		left: 50%;
		bottom: 1rem;
		z-index: 70;
		display: flex;
		width: min(calc(100vw - 2rem), 44rem);
		transform: translateX(-50%);
		align-items: center;
		justify-content: space-between;
		gap: 0.875rem;
		border: 1px solid var(--warm-ring);
		border-radius: 999px;
		background: color-mix(in oklab, var(--color-surface-raised) 94%, var(--color-warm));
		box-shadow: var(--glow-warm);
		padding: 0.625rem 0.75rem 0.625rem 0.875rem;
		color: var(--color-ink-0);
	}

	.mockup-copy {
		display: flex;
		min-width: 0;
		align-items: center;
		gap: 0.625rem;
	}

	.mockup-actions {
		display: flex;
		flex-shrink: 0;
		align-items: center;
		gap: 0.5rem;
	}

	.mockup-message {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.8125rem;
		color: var(--color-ink-1);
	}

	@media (max-width: 640px) {
		.mockup-banner {
			align-items: stretch;
			border-radius: 1.25rem;
			flex-direction: column;
		}
		.mockup-message {
			white-space: normal;
		}
	}
</style>
