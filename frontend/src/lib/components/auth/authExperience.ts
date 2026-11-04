import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceMessage, experienceState, recordExperience, type ExperienceAction, type ExperienceComponent, type ExperienceContext } from '$lib/utils/experience';
import { resolveExperienceMessage, type Translator } from '$lib/i18n/runtime.svelte';
import type { MessageValues } from '$lib/i18n/messageFormat';
import { unavailableExperienceMessage } from '$lib/i18n/experienceMessages';
export type { ExperienceContext } from '$lib/utils/experience';

export interface AuthExperience {
	context: ExperienceContext | undefined;
	options: { experience?: ExperienceContext };
	state(state: 'loading' | 'ready' | 'empty' | 'error' | 'disabled', step?: number): void;
	validation(reason: 'required' | 'policy' | 'format' | 'authority' | 'unknown'): void;
	discard(reason?: 'stale' | 'aborted' | 'scope_changed' | 'unmounted' | 'unknown'): void;
	applied(isCurrentState?: () => boolean): Promise<void>;
	message(namespace: string, key: string, tone?: 'neutral' | 'info' | 'success' | 'warning' | 'danger'): void;
	unknownMessage(): void;
}
export function beginAuthExperience(component: ExperienceComponent, action: ExperienceAction, owns: () => boolean, feature: 'auth' | 'account' | 'mcp' | 'iam' = 'auth', inherited?: ExperienceContext): AuthExperience {
	const context = inherited ?? (action === 'load' || action === 'view' ? beginExperienceLoad(feature, component) : beginExperienceAction(feature, action, component));
	return {
		context,
		options: context ? { experience: context } : {},
		state(state: 'loading' | 'ready' | 'empty' | 'error' | 'disabled', step?: number) { if (owns()) experienceState(context, state, step); },
		validation(reason: 'required' | 'policy' | 'format' | 'authority' | 'unknown') { if (owns()) recordExperience(context, 'validation.rejected', { reason }); },
		discard(reason: 'stale' | 'aborted' | 'scope_changed' | 'unmounted' | 'unknown' = 'stale') { experienceDiscarded(context, reason); },
		async applied(isCurrentState?: () => boolean) {
			if (!owns()) return;
			await experienceApplied(context, undefined, () => owns() && (isCurrentState?.() ?? true));
		},
		message(namespace: string, key: string, tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger' = 'danger') {
			if (owns()) experienceMessage(context, { ...resolveExperienceMessage(namespace, key), tone });
		},
		unknownMessage() { if (owns()) experienceMessage(context, unavailableExperienceMessage('danger')); },
	};
}

/** Metadata is resolved at formatting time; values/text never enter the collector. */
export function observedAuthText<Key extends string>(observation: AuthExperience, namespace: string, translate: Translator<Key>) {
	return (key: Key, values?: MessageValues) => {
		const text = translate(key, values);
		observation.message(namespace, key);
		return text;
	};
}

/** A visible notice slot retains its producer across unrelated actions and locale re-renders. */
export function createAuthNoticePresenter() {
	const visible = new Map<string, { source: string; resolved: string; producer: AuthExperience | undefined }>();
	return (slot: string, observation: AuthExperience | undefined, namespace: string, key: string | null, tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger' = 'info') => {
		if (key === null) { visible.delete(slot); return; }
		if (!observation) return;
		const metadata = resolveExperienceMessage(namespace, key);
		const source = [namespace, key, tone].join('\u0000');
		let previous = visible.get(slot);
		if (!previous || previous.source !== source) {
			previous = { source, resolved: '', producer: observation };
			visible.set(slot, previous);
		}
		const resolved = [metadata.locale, metadata.catalog_revision, metadata.restoration].join('\u0000');
		if (previous.resolved === resolved) return;
		previous.resolved = resolved;
		previous.producer?.message(namespace, key, tone);
	};
}
