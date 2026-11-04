import { ApiError } from './client';
import { toast } from '$lib/stores/toast';
import { t } from '$lib/i18n/ns/shared';
import { resolveExperienceMessage } from '$lib/i18n/runtime.svelte';
import { unavailableExperienceMessage } from '$lib/i18n/experienceMessages';
import type { ExperienceContext } from '$lib/utils/experience';

export interface ApiMutOpts {
	experience?: ExperienceContext;
	successMessage?: string | null;
	errorPrefix?: string;
	progress?: boolean;
	rethrow?: boolean;
}

function mutationMessage(key: string) {
	const metadata = resolveExperienceMessage('shared', key);
	return metadata.restoration === 'restored'
		? { ...metadata, restoration: 'redacted' as const }
		: metadata;
}

export async function apiMut<T>(
	label: string,
	fn: () => Promise<T>,
	opts: ApiMutOpts = {}
): Promise<T> {
	const { successMessage, errorPrefix, progress = false, rethrow = true, experience } = opts;
	let progressId: string | undefined;
	if (progress) {
		const message = t('mutation.progress', { label });
		progressId = experience
			? toast.info(message, 0, undefined, { context: experience, message: mutationMessage('mutation.progress') })
			: toast.info(message, 0);
	}
	try {
		const result = await fn();
		if (progressId) toast.remove(progressId);
		if (successMessage !== null) {
			const message = successMessage ?? t('mutation.completed', { label });
			if (experience) {
				const metadata = successMessage === undefined
					? mutationMessage('mutation.completed')
					: unavailableExperienceMessage('success');
				toast.success(message, undefined, undefined, { context: experience, message: metadata });
			} else toast.success(message);
		}
		return result;
	} catch (e) {
		if (progressId) toast.remove(progressId);
		const msg = e instanceof ApiError ? e.message : String(e);
		const message = errorPrefix == null
			? t('mutation.failed', { label, message: msg })
			: t('mutation.failedWithPrefix', { prefix: errorPrefix, message: msg });
		if (experience) {
			const key = errorPrefix == null ? 'mutation.failed' : 'mutation.failedWithPrefix';
			const metadata = mutationMessage(key);
			toast.error(message, undefined, undefined, { context: experience, message: metadata });
		} else toast.error(message);
		if (rethrow) throw e;
		return undefined as T;
	}
}
