<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-system';
	import { auth } from '$lib/stores/auth';
	import AdminLoginBrandingPanel from '$lib/components/admin/AdminLoginBrandingPanel.svelte';
	import AdminResourcePoliciesPanel from '$lib/components/admin/AdminResourcePoliciesPanel.svelte';
	import { Card, PageHeader, PageShell } from '$lib/components/ui';

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
</script>

<PageShell max="7xl">
	<PageHeader
		breadcrumb={t('settings.breadcrumb')}
		title={t('settings.title')}
		subtitle={t('settings.subtitle')}
	/>

	<div class="settings-stack">
		<Card padding="lg" surface="subtle">
			<div class="settings-intro">
				<p class="eyebrow">{t('settings.eyebrow')}</p>
				<h2>{t('settings.defaults')}</h2>
				<p>
					{t('settings.description')}
				</p>
			</div>
		</Card>

		<AdminLoginBrandingPanel {token} {projectId} />
		<AdminResourcePoliciesPanel {token} {projectId} />
	</div>
</PageShell>

<style>
	.settings-stack {
		display: grid;
		gap: 1rem;
	}

	.settings-intro {
		display: grid;
		gap: 0.35rem;
		max-width: 42rem;
	}

	.eyebrow {
		margin: 0;
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--admin-tone, var(--color-warm));
	}

	h2 {
		margin: 0;
		font-size: 1rem;
		font-weight: 700;
		color: var(--color-ink-0);
	}

	p {
		margin: 0;
		font-size: 0.85rem;
		line-height: 1.6;
		color: var(--color-ink-2);
	}
</style>
