import type { AvailableDomain } from '$lib/types/auth';

export type PostLoginTarget = '/dashboard' | '/select-project' | '/select-domain';

export interface PostLoginProjectInput {
	project_id?: string | null;
	default_project_id?: string | null;
}

export interface PostLoginProjectResolution {
	projectId: string | null;
	target: PostLoginTarget;
}

function normalizeProjectId(value: string | null | undefined): string | null {
	const trimmed = value?.trim() ?? '';
	return trimmed.length > 0 ? trimmed : null;
}

export function resolvePostLoginProject(input: PostLoginProjectInput): PostLoginProjectResolution {
	const projectId = normalizeProjectId(input.project_id);
	if (projectId) {
		return { projectId, target: '/dashboard' };
	}

	return { projectId: null, target: '/select-project' };
}

/** Existing-session navigation only. Fresh authentication always opens the workspace chooser. */
export function loginDestination(state: { availableDomains?: AvailableDomain[]; projectId?: string | null }): PostLoginTarget {
	if (normalizeProjectId(state.projectId)) return '/dashboard';
	if ((state.availableDomains?.length ?? 0) > 1) return '/select-domain';
	return '/select-project';
}
