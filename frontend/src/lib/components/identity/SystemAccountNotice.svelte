<script lang="ts">
	import type { SystemAccountIdentity } from '$lib/types/common';
	import { isSystemAccount } from '$lib/utils/systemAccount';
	import { t } from '$lib/i18n/ns/common';
	import Pill from '$lib/components/ui/Pill.svelte';

	let { identity }: { identity: SystemAccountIdentity | null | undefined } = $props();
</script>

{#if isSystemAccount(identity)}
	<details class="min-w-0 max-w-full text-sm text-ink-2" data-system-account="auto_backup">
		<summary class="min-h-11 cursor-pointer py-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
			<Pill tone="neutral"><span class="whitespace-normal [overflow-wrap:anywhere]">{t('systemAccount.autoBackup')}</span></Pill>
		</summary>
		<p class="max-w-prose whitespace-normal pb-2 [overflow-wrap:anywhere]">{t('systemAccount.managedHelp')}</p>
	</details>
{/if}
