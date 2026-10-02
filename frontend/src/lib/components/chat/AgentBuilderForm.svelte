<script lang="ts">
	import type { AgentForm, AgentExtension } from '$lib/api/chatAgents';
	import { isAvatarUrl } from '$lib/api/chatAgents';
	import type { AvailableModel } from '$lib/api/chatTree';
	import Button from '$lib/components/ui/Button.svelte';
	import { t } from '$lib/i18n/ns/chat-settings';
	import RichText from '$lib/i18n/RichText.svelte';

	interface Props {
		form: AgentForm;
		models: AvailableModel[];
		mcps: AgentExtension[];
		tools: AgentExtension[];
		editing?: boolean;
		saving?: boolean;
		onSubmit: () => void;
		onCancel: () => void;
	}
	let {
		form = $bindable(),
		models,
		mcps,
		tools,
		editing = false,
		saving = false,
		onSubmit,
		onCancel
	}: Props = $props();

	const canSubmit = $derived(form.name.trim().length > 0 && !saving);
</script>

<form
	class="builder"
	onsubmit={(e) => {
		e.preventDefault();
		if (canSubmit) onSubmit();
	}}
>
	<div class="row two">
		<label class="field avatar-field">
			{#snippet avatarHint(text: string)}<span class="hint">{text}</span>{/snippet}
			<span class="lbl"><RichText segments={t.rich('agentBuilder.avatar.label')} tags={{ hint: avatarHint }} /></span>
			<div class="avatar-row">
				<span class="avatar-preview">
					{#if isAvatarUrl(form.avatar)}
						<img src={form.avatar} alt={t('agentBuilder.avatar.alt')} />
					{:else if form.avatar.trim()}
						{form.avatar}
					{:else}
						🤖
					{/if}
				</span>
				<input class="inp" bind:value={form.avatar} placeholder={t('agentBuilder.avatar.placeholder')} />
			</div>
		</label>
		<label class="field">
			<span class="lbl">{t('agentBuilder.name.label')} <span class="req">*</span></span>
			<input class="inp" bind:value={form.name} placeholder={t('agentBuilder.name.placeholder')} required />
		</label>
	</div>

	<label class="field">
		<span class="lbl">{t('agentBuilder.description.label')}</span>
		<input class="inp" bind:value={form.description} placeholder={t('agentBuilder.description.placeholder')} />
	</label>

	<label class="field">
		<span class="lbl">{t('agentBuilder.instructions.label')}</span>
		<textarea class="inp ta" bind:value={form.instructions} rows="5" placeholder={t('agentBuilder.instructions.placeholder')}></textarea>
	</label>

	<div class="row three">
		<label class="field">
			<span class="lbl">{t('agentBuilder.model.label')}</span>
			<select class="inp" bind:value={form.model_name}>
				<option value="">{t('agentBuilder.model.default')}</option>
				{#each models as m (m.model_name)}
					<option value={m.model_name}>{m.display_name}{m.provider ? ` · ${m.provider}` : ''}</option>
				{/each}
			</select>
		</label>
		<label class="field">
			<span class="lbl">{t('agentBuilder.temperature.label')}</span>
			<input class="inp" bind:value={form.temperature} inputmode="decimal" placeholder={t('agentBuilder.temperature.placeholder')} />
		</label>
		<label class="field">
			<span class="lbl">{t('agentBuilder.maxTokens.label')}</span>
			<input class="inp" bind:value={form.max_tokens} inputmode="numeric" placeholder={t('agentBuilder.maxTokens.placeholder')} />
		</label>
	</div>

	<div class="row two">
		<div class="field">
			<span class="lbl">{t('agentBuilder.mcp.label')}</span>
			<div class="checklist">
				{#if mcps.length === 0}
					<p class="empty">{t('agentBuilder.mcp.empty')}</p>
				{:else}
					{#each mcps as s (s.id)}
						<label class="check">
							<input type="checkbox" bind:checked={form.mcp_ids[s.id]} />
							<span class="truncate">{s.name}</span>
						</label>
					{/each}
				{/if}
			</div>
		</div>
		<div class="field">
			<span class="lbl">{t('agentBuilder.tools.label')}</span>
			<div class="checklist">
				{#if tools.length === 0}
					<p class="empty">{t('agentBuilder.tools.empty')}</p>
				{:else}
					{#each tools as tool (tool.id)}
						<label class="check">
							<input type="checkbox" bind:checked={form.tool_ids[tool.id]} />
							<span class="truncate">{tool.name}</span>
						</label>
					{/each}
				{/if}
			</div>
		</div>
	</div>

	<div class="field">
		<span class="lbl">{t('agentBuilder.visibility.label')}</span>
		<div class="visibility">
			<button
				type="button"
				class="vis-opt"
				class:active={form.visibility === 'private'}
				onclick={() => (form.visibility = 'private')}
			>
				<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>
				{t('agentBuilder.visibility.private')}
			</button>
			<button
				type="button"
				class="vis-opt"
				class:active={form.visibility === 'public'}
				onclick={() => (form.visibility = 'public')}
			>
				<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18z" /></svg>
				{t('agentBuilder.visibility.public')}
			</button>
		</div>
	</div>

	<div class="actions">
		<Button variant="ghost" type="button" onclick={onCancel}>{t('agentBuilder.actions.cancel')}</Button>
		<Button variant="accent" type="submit" disabled={!canSubmit}>
			{saving ? t('agentBuilder.actions.saving') : editing ? t('agentBuilder.actions.saveChanges') : t('agentBuilder.actions.create')}
		</Button>
	</div>
</form>

<style>
	.builder {
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}
	.row {
		display: grid;
		gap: 0.9rem;
	}
	.row.two {
		grid-template-columns: 1fr 1fr;
	}
	.row.three {
		grid-template-columns: 1fr 1fr 1fr;
	}
	.field {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		min-width: 0;
	}
	.lbl {
		font-size: 0.75rem;
		font-weight: 550;
		color: var(--color-ink-2);
	}
	.hint {
		font-weight: 400;
		color: var(--color-ink-2);
	}
	.req {
		color: var(--color-state-danger);
	}
	.inp {
		width: 100%;
		border-radius: 0.5rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
		padding: 0.5rem 0.65rem;
		font-size: 0.8125rem;
		color: var(--color-ink-1);
	}
	.inp:focus {
		outline: none;
		border-color: var(--color-accent);
	}
	.ta {
		resize: vertical;
		min-height: 5rem;
		line-height: 1.5;
		font-family: inherit;
	}
	.avatar-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.avatar-preview {
		flex-shrink: 0;
		width: 2.3rem;
		height: 2.3rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 0.6rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-sunken);
		font-size: 1.1rem;
		overflow: hidden;
	}
	.avatar-preview img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.checklist {
		max-height: 8rem;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		padding: 0.4rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
	}
	.check {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.25rem 0.35rem;
		border-radius: 0.35rem;
		font-size: 0.8125rem;
		color: var(--color-ink-1);
		cursor: pointer;
	}
	.check:hover {
		background: var(--color-surface-sunken);
	}
	.empty {
		padding: 0.4rem 0.35rem;
		font-size: 0.78rem;
		color: var(--color-ink-2);
	}
	.truncate {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.visibility {
		display: flex;
		gap: 0.5rem;
	}
	.vis-opt {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.45rem 0.8rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-base);
		color: var(--color-ink-2);
		font-size: 0.8125rem;
		cursor: pointer;
		transition: background 0.12s, color 0.12s, border-color 0.12s;
	}
	.vis-opt:hover {
		color: var(--color-ink-0);
	}
	.vis-opt.active {
		border-color: var(--color-accent);
		color: var(--color-accent);
		background: color-mix(in oklab, var(--color-accent) 10%, transparent);
	}
	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
		padding-top: 0.3rem;
	}
	@media (max-width: 540px) {
		.row.two,
		.row.three {
			grid-template-columns: 1fr;
		}
	}
</style>
