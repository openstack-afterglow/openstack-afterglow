<script lang="ts">
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { t } from '$lib/i18n/ns/public-entry';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import {
		consentCloudAccess, nativeCloudAccess, consentServiceAccess, consentServiceLabelKey, consentServiceReasonKey,
		operationsAccess, MCP_CONSENT_SERVICES, type McpConsentProject, type McpOperation,
	} from '$lib/utils/mcpConsentPermissions';

	let { projects, accessLevel = 'read', operations, title, headingLevel = 2 }: {
		projects: McpConsentProject[];
		accessLevel?: 'read' | 'manage';
		// Per-project operations (OAuth consent) take precedence over one grant-wide level.
		operations?: Record<string, McpOperation[]>;
		title?: string;
		headingLevel?: 2 | 3;
	} = $props();
	const headingId = $props.id();

	function accessFor(project: McpConsentProject): 'read' | 'manage' {
		return operations ? operationsAccess(operations[project.id] ?? []) : accessLevel;
	}
	function operationList(project: McpConsentProject): string {
		const chosen = operations?.[project.id] ?? [];
		return new Intl.ListFormat(intlLocale(), { type: 'conjunction', style: 'narrow' })
			.format(chosen.map((operation) => t(`mcpConsent.operations.${operation}`)));
	}
</script>

<section class="permission-preview" aria-labelledby={headingId}>
	<svelte:element this={headingLevel === 3 ? 'h3' : 'h2'} id={headingId} class="preview-heading">{title ?? t('mcpConsent.preview.title')}</svelte:element>
	<p>{t('mcpConsent.preview.help')}</p>
	<ul class="preview-projects">
		{#each projects as project (project.id)}
			{@const access = accessFor(project)}
			{@const cloudAccess = consentCloudAccess(project, access)}
			{@const cloudCapability = nativeCloudAccess(project)}
			<li class="preview-project" aria-label={`${project.name} ${project.id}`}>
				<div class="preview-project-heading">
					<svelte:element this={headingLevel === 3 ? 'h4' : 'h3'} class="project-name">{project.name}<code>{project.id}</code></svelte:element>
				</div>
				<dl class="cloud-permissions">
					<div class="cloud-permission" data-cloud-authority="native">
						<dt>{t('mcpConsent.preview.nativeCloud')}</dt>
						<dd><StatusChip status={cloudCapability} label={t(`mcpConsent.preview.nativeCloudAccess.${cloudCapability}`)} /></dd>
					</div>
					<div class="cloud-permission" data-cloud-authority="effective">
						<dt>{t('mcpConsent.preview.effectiveCloud')}</dt>
						<dd>
							{#if operations && cloudAccess !== 'unknown'}
								<StatusChip status={access} label={operationList(project)} />
							{:else}
								<StatusChip status={cloudAccess} label={t(`mcpConsent.preview.cloud.${cloudAccess}`)} />
							{/if}
						</dd>
					</div>
				</dl>
				{#if project.scope_error}
					<p class="permission-unavailable">{t('mcpConsent.preview.scopeUnavailable')}</p>
				{:else}
				<details class="service-details">
					<summary>{t('mcpConsent.preview.serviceDetails')}</summary>
					<dl class="service-permissions">
						{#each MCP_CONSENT_SERVICES as service (service.id)}
							{@const native = consentServiceAccess(project, service.id, access)}
							<div class="service-permission">
								<dt>{service.name}</dt>
								<dd>
									{#if native.state === 'allowed'}
										<ul class="permission-leaves">
											{#each native.leaves as leaf}
												{@const labelKey = consentServiceLabelKey(leaf)}
												<li>{#if labelKey}<span>{t(labelKey)}</span>{/if}<code>{leaf}</code></li>
											{/each}
										</ul>
									{:else}
										<span class:permission-unavailable={native.state === 'unavailable'}>{native.state === 'unavailable' ? t(consentServiceReasonKey(native.reason)) : t(`mcpConsent.preview.service.${native.state}`)}</span>
									{/if}
								</dd>
							</div>
						{/each}
					</dl>
				</details>
				{/if}
			</li>
		{/each}
	</ul>
</section>

<style>
	.permission-preview { min-width: 0; }
	.preview-heading { margin: 0; color: var(--color-ink-0); font-size: 1rem; font-weight: 600; }
	.permission-preview > p { margin: 0.5rem 0 0.75rem; color: var(--color-ink-2); font-size: var(--type-support); line-height: 1.5; }
	.preview-projects { display: grid; gap: 1rem; margin: 0; padding: 0; list-style: none; }
	.preview-project { min-width: 0; padding-block: 0.75rem; border-top: 1px solid var(--color-line); }
	.preview-project-heading { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 0.5rem; }
	.project-name { min-width: 0; margin: 0; color: var(--color-ink-0); font-size: var(--type-body); overflow-wrap: anywhere; }
	.project-name code { display: block; margin-top: 0.25rem; color: var(--color-ink-2); font-size: var(--type-identifier); font-weight: 400; }
	.cloud-permissions { display: grid; gap: 0.5rem; margin: 0.75rem 0 0; font-size: var(--type-support); }
	.cloud-permission { display: grid; grid-template-columns: minmax(0, 12rem) minmax(0, 1fr); align-items: start; gap: 0.75rem; }
	.cloud-permission dt { color: var(--color-ink-1); overflow-wrap: anywhere; }
	.cloud-permission dd { min-width: 0; margin: 0; }
	.cloud-permission :global(.chip .label) { white-space: normal; overflow-wrap: anywhere; }
	.service-details { margin-top: 0.75rem; font-size: var(--type-support); }
	.service-details summary { width: fit-content; color: var(--color-ink-1); cursor: pointer; }
	.service-permissions { display: grid; gap: 0.75rem; margin: 0.75rem 0 0; }
	.service-permission { display: grid; grid-template-columns: minmax(0, 6rem) minmax(0, 1fr); gap: 0.75rem; }
	.service-permission dt { color: var(--color-ink-1); font-weight: 600; overflow-wrap: anywhere; }
	.service-permission dd { min-width: 0; margin: 0; color: var(--color-ink-2); overflow-wrap: anywhere; }
	.permission-leaves { display: grid; gap: 0.25rem; margin: 0; padding: 0; list-style: none; }
	.permission-leaves li { display: grid; gap: 0.125rem; }
	.permission-leaves span { color: var(--color-ink-1); }
	.permission-leaves code { color: var(--color-ink-2); font-size: var(--type-identifier); }
	.permission-unavailable { color: var(--color-state-warning-text); }
	.preview-project > p { margin: 0.75rem 0 0; font-size: var(--type-support); line-height: 1.5; overflow-wrap: anywhere; }
	@media (max-width: 767px) {
		.cloud-permission, .service-permission { grid-template-columns: minmax(0, 1fr); gap: 0.25rem; }
	}
</style>
