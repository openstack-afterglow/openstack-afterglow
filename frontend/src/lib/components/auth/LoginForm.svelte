<script lang="ts">
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import GitLabLoginButton from './GitLabLoginButton.svelte';

	let {
		domainName = $bindable(),
		username = $bindable(),
		password = $bindable(),
		error,
		loading,
		gitlabEnabled,
		gitlabLoading,
		onSubmit,
		onGitlab,
	}: {
		domainName: string;
		username: string;
		password: string;
		error: string;
		loading: boolean;
		gitlabEnabled: boolean;
		gitlabLoading: boolean;
		onSubmit: () => Promise<void>;
		onGitlab: () => Promise<void>;
	} = $props();
</script>

<form
	onsubmit={(e) => { e.preventDefault(); onSubmit(); }}
	class="login-form"
>
	{#if error}
		<Alert tone="danger">{error}</Alert>
	{/if}

	<Field label="도메인" for="domain">
		<TextInput id="domain" bind:value={domainName} type="text" />
	</Field>

	<Field label="사용자명" for="username" required>
		<TextInput id="username" bind:value={username} type="text" required />
	</Field>

	<Field label="비밀번호" for="password" required>
		<TextInput
			id="password"
			bind:value={password}
			type="password"
			required
			onkeydown={(e) => { if (e.key === 'Enter' && !loading) { e.preventDefault(); onSubmit(); } }}
		/>
	</Field>

	<Button type="submit" disabled={loading} class="login-submit" size="lg">
		{loading ? '로그인 중...' : '로그인'}
	</Button>

	<GitLabLoginButton enabled={gitlabEnabled} loading={gitlabLoading} onClick={onGitlab} />
</form>

<style>
	.login-form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		border: 1px solid var(--color-line-2);
		border-radius: 0.75rem;
		background: var(--color-surface-raised);
		padding: 2rem;
	}
</style>
