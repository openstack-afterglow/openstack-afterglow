<script lang="ts">
	import { onDestroy } from 'svelte';
	import { auth, authReady } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import { createAuthVerificationController } from '../authVerification';
	import { loginDestination } from '../authFlow';

	const verification = createAuthVerificationController();
	$effect(() => { verification.setEnabled(true); });
	onDestroy(() => verification.dispose());
	$effect(() => {
		if ($authReady && $auth.token) {
			void api.get('/protected-resource', $auth.token, $auth.projectId ?? undefined);
		}
	});
</script>

{#if !$auth.token}
	<p role="status">Signed out</p>
{:else if !$authReady}
	<p role="status">Verifying session</p>
{:else}
	<p role="status">{loginDestination($auth)} · {$auth.userId} · {$auth.domainId} · {$auth.projectId ?? 'none'}</p>
	<input aria-label="Unsubmitted draft" />
{/if}
