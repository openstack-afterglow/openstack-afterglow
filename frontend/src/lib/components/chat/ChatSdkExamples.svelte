<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import { t } from '$lib/i18n/ns/chat-settings';
	import { getLocale } from '$lib/i18n/runtime.svelte';
	import { toast } from '$lib/stores/toast';

	let { baseUrl }: { baseUrl: string } = $props();
	const id = $props.id();
	const providers = {
		openai: { label: 'OpenAI', python: 'openai', node: 'openai' },
		anthropic: { label: 'Anthropic', python: 'anthropic', node: '@anthropic-ai/sdk' },
		gemini: { label: 'Gemini', python: 'google-genai', node: '@google/genai' }
	};
	const languages = { python: 'Python', node: 'JavaScript', curl: 'curl' };
	type Provider = keyof typeof providers;
	type Language = keyof typeof languages;
	let provider = $state<Provider>('openai');
	let language = $state<Language>('python');
	const providerTabs = Object.entries(providers).map(([value, { label }]) => ({ value, label, panelId: `${id}-provider-panel` }));
	const languageTabs = Object.entries(languages).map(([value, label]) => ({ value, label, panelId: `${id}-language-panel` }));
	const tutorialUrl = $derived(`https://openstack-afterglow.github.io/openstack-afterglow/${getLocale() === 'ko' ? '' : 'en/'}lumen-sdk.html`);
	const installCommand = $derived(language === 'python' ? `python -m pip install ${providers[provider].python}` : `npm install ${providers[provider].node}`);
	const example = $derived(buildExample(baseUrl, provider, language));

	function buildExample(baseUrl: string, provider: Provider, language: Language): string {
		const sdkBase = JSON.stringify(provider === 'openai' ? `${baseUrl}/v1` : baseUrl);
		if (language === 'curl') {
			const path = provider === 'gemini' ? 'v1beta/models' : 'v1/models';
			const headers = provider === 'anthropic'
				? ['x-api-key: $LUMEN_API_KEY', 'anthropic-version: 2023-06-01']
				: [provider === 'gemini' ? 'x-goog-api-key: $LUMEN_API_KEY' : 'Authorization: Bearer $LUMEN_API_KEY'];
			return [`curl --fail-with-body --silent --show-error '${baseUrl}/${path}'`, ...headers.map((header) => `  -H "${header}"`)].join(' \\\n');
		}
		if (language === 'python') {
			const client = provider === 'gemini'
				? `from google import genai\nfrom google.genai.types import HttpOptions\n\nclient = genai.Client(\n    api_key=os.environ["LUMEN_API_KEY"],\n    http_options=HttpOptions(base_url=${sdkBase}, api_version="v1beta"),\n)`
				: `from ${provider} import ${provider === 'openai' ? 'OpenAI' : 'Anthropic'}\n\nclient = ${provider === 'openai' ? 'OpenAI' : 'Anthropic'}(\n    api_key=os.environ["LUMEN_API_KEY"],\n    base_url=${sdkBase},\n)`;
			return `import os\n\n${client}\nfor model in client.models.list():\n    print(model.${provider === 'gemini' ? 'name' : 'id'})`;
		}
		const name = { openai: 'OpenAI', anthropic: 'Anthropic', gemini: 'GoogleGenAI' }[provider];
		const client = provider === 'gemini'
			? `import { GoogleGenAI } from '@google/genai';\n\nconst client = new GoogleGenAI({\n  apiKey: process.env.LUMEN_API_KEY,\n  httpOptions: { baseUrl: ${sdkBase}, apiVersion: 'v1beta' },\n});`
			: `import ${name} from '${providers[provider].node}';\n\nconst client = new ${name}({\n  apiKey: process.env.LUMEN_API_KEY,\n  baseURL: ${sdkBase},\n});`;
		return `${client}\n\nfor await (const model of await client.models.list(${provider === 'gemini' ? '{}' : ''})) {\n  console.log(model.${provider === 'gemini' ? 'name' : 'id'});\n}`;
	}

	async function copyExample() {
		try {
			await navigator.clipboard.writeText(example);
			toast.success(t('apiKeys.toast.copied'));
		} catch {
			toast.error(t('apiKeys.toast.copyFailed'));
		}
	}
</script>

<section class="mt-5 min-w-0 border-t border-[var(--color-line)] pt-5">
	<div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
		<h5 class="text-sm font-semibold text-ink-1">{t('apiKeys.sdk.title')}</h5>
		<Button href={tutorialUrl} variant="link" size="sm">{t('apiKeys.sdk.tutorial')}</Button>
	</div>
	<p class="mt-1 text-sm leading-6 text-ink-2">{t('apiKeys.sdk.help', { apiKey: 'LUMEN_API_KEY', scope: 'models:read' })}</p>
	<Tabs id={`${id}-provider`} value={provider} items={providerTabs} ariaLabel={t('apiKeys.sdk.provider')} class="mt-3"
		onchange={(value) => { provider = value as Provider; }} />
	<div id={`${id}-provider-panel`} role="tabpanel" aria-labelledby={`${id}-provider-${provider}`} class="min-w-0">
		<Tabs id={`${id}-language`} value={language} items={languageTabs} ariaLabel={t('apiKeys.sdk.language')}
			onchange={(value) => { language = value as Language; }} />
		<div id={`${id}-language-panel`} role="tabpanel" aria-labelledby={`${id}-language-${language}`} class="min-w-0">
			<div class="my-2 flex min-w-0 flex-wrap items-center justify-end gap-2">
				{#if language !== 'curl'}
					<code class="mr-auto break-all text-xs text-ink-2">{installCommand}</code>
				{/if}
				<Button variant="ghost" size="sm" onclick={copyExample}>{t('apiKeys.sdk.copy')}</Button>
			</div>
			<pre class="max-w-full overflow-x-auto rounded-lg bg-[var(--color-surface-sunken)] p-3 font-mono text-xs text-ink-2" role="region" aria-label={`${providers[provider].label} · ${languages[language]}`}><code>{example}</code></pre>
		</div>
	</div>
</section>
