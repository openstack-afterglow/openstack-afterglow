import { api, ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/instance';
import { confirmDialog } from '$lib/stores/confirm.svelte';
import { toast } from '$lib/stores/toast';

interface DeletionTarget {
	id: string;
	name?: string | null;
	upperVolume?: boolean;
}

interface DeletionConfirmationOptions {
	targets: readonly DeletionTarget[];
	adminMode: boolean;
	token: string | undefined;
	projectId: string | undefined;
	isCurrent: () => boolean;
	includeRetainedVolumes?: boolean;
}

interface DeletionVolume {
	volume_id: string;
	name?: string | null;
	device?: string | null;
	delete_on_termination: boolean;
}

export async function confirmInstanceDeletion(message: string, options: DeletionConfirmationOptions): Promise<boolean> {
	if (!options.targets.length || !options.isCurrent()) return false;
	const lines = [message];
	let requiresText = false;
	try {
		for (const target of options.targets) {
			if (!options.isCurrent()) return false;
			const volumes = await api.get<DeletionVolume[]>(
				`/api/v1/${options.adminMode ? 'admin/' : ''}instances/${encodeURIComponent(target.id)}/volumes`,
				options.token,
				options.projectId,
				{ refresh: true, cache: 'no-store' },
			);
			if (!options.isCurrent()) return false;
			if (!Array.isArray(volumes) || volumes.some(volume => !volume || typeof volume.delete_on_termination !== 'boolean')) {
				throw new Error(t('controller.error.server'));
			}
			const autoDeleteVolumes = volumes.filter(volume => volume.delete_on_termination === true);
			const retainedVolumes = volumes.filter(volume => volume.delete_on_termination === false);
			const label = options.targets.length > 1 ? `${target.name || target.id}: ` : '';
			if (autoDeleteVolumes.length) {
				requiresText = true;
				lines.push(label + t('controller.delete.autoDeleteVolumes', { volumes: autoDeleteVolumes.map(volume => volume.name || volume.device || volume.volume_id).join(', ') }));
			}
			if (options.includeRetainedVolumes && retainedVolumes.length) {
				lines.push(label + t('controller.delete.keepVolumes', { volumes: retainedVolumes.map(volume => volume.name || volume.device || volume.volume_id).join(', ') }));
			}
			if (target.upperVolume) lines.push(label + t('controller.delete.upperVolumeNotice'));
		}
	} catch (error) {
		if (options.isCurrent()) toast.error(t('controller.error.fetchFailed', {
			status: error instanceof ApiError ? error.status : 0,
			message: error instanceof Error ? error.message : t('controller.error.server'),
		}));
		return false;
	}
	if (!options.isCurrent()) return false;
	if (!requiresText) return confirmDialog(lines.join('\n'));
	const requiredText = t('controller.delete.requiredText');
	return confirmDialog(lines.join('\n'), {
		requiredText,
		requiredTextLabel: t('controller.delete.requiredTextLabel', { text: requiredText }),
	});
}
