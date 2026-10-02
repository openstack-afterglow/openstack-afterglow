import { ApiError } from './client';
import { toast } from '$lib/stores/toast';
import { t } from '$lib/i18n/ns/shared';

export interface ApiMutOpts {
	successMessage?: string | null;
	errorPrefix?: string;
	progress?: boolean;
	rethrow?: boolean;
}

export async function apiMut<T>(
	label: string,
	fn: () => Promise<T>,
	opts: ApiMutOpts = {}
): Promise<T> {
	const { successMessage, errorPrefix, progress = false, rethrow = true } = opts;
	let progressId: string | undefined;
	if (progress) progressId = toast.info(t('mutation.progress', { label }), 0);
	try {
		const result = await fn();
		if (progressId) toast.remove(progressId);
		if (successMessage !== null) toast.success(successMessage ?? t('mutation.completed', { label }));
		return result;
	} catch (e) {
		if (progressId) toast.remove(progressId);
		const msg = e instanceof ApiError ? e.message : String(e);
		toast.error(errorPrefix == null
			? t('mutation.failed', { label, message: msg })
			: t('mutation.failedWithPrefix', { prefix: errorPrefix, message: msg }));
		if (rethrow) throw e;
		return undefined as T;
	}
}
