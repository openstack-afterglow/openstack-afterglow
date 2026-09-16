export type ServiceColumn =
	| { type: 'binary'; label: string }
	| { type: 'host'; label: string }
	| { type: 'zone'; label: string }
	| { type: 'status'; label: string }
	| { type: 'state'; label: string }
	| { type: 'disabledReason'; label: string }
	| { type: 'updated'; label: string };

export function fmtTime(s: string | null): string {
	if (!s) return '-';
	return s.slice(0, 19).replace('T', ' ');
}

const FULL_COLUMNS: ServiceColumn[] = [
	{ type: 'binary', label: 'Binary' },
	{ type: 'host', label: 'Host' },
	{ type: 'zone', label: 'Zone' },
	{ type: 'status', label: 'Status' },
	{ type: 'state', label: 'State' },
	{ type: 'disabledReason', label: 'Disabled Reason' },
	{ type: 'updated', label: 'Updated' },
];

export const COMPUTE_COLUMNS: ServiceColumn[] = FULL_COLUMNS;
export const BLOCK_STORAGE_COLUMNS: ServiceColumn[] = FULL_COLUMNS;

export const SHARED_FS_COLUMNS: ServiceColumn[] = [
	{ type: 'binary', label: 'Binary' },
	{ type: 'host', label: 'Host' },
	{ type: 'zone', label: 'Zone' },
	{ type: 'status', label: 'Status' },
	{ type: 'state', label: 'State' },
	{ type: 'updated', label: 'Updated' },
];

export const ORCHESTRATION_COLUMNS: ServiceColumn[] = [
	{ type: 'binary', label: 'Binary' },
	{ type: 'host', label: 'Host' },
	{ type: 'status', label: 'Status' },
	{ type: 'state', label: 'State' },
	{ type: 'updated', label: 'Updated' },
];

export const CONTAINER_COLUMNS: ServiceColumn[] = [
	{ type: 'binary', label: 'Binary' },
	{ type: 'host', label: 'Host' },
	{ type: 'zone', label: 'Zone' },
	{ type: 'status', label: 'Status' },
	{ type: 'state', label: 'State' },
	{ type: 'updated', label: 'Updated' },
];

export const CONTAINER_INFRA_COLUMNS: ServiceColumn[] = [
	{ type: 'binary', label: 'Binary' },
	{ type: 'host', label: 'Host' },
	{ type: 'status', label: 'Status' },
	{ type: 'state', label: 'State' },
	{ type: 'disabledReason', label: 'Disabled Reason' },
	{ type: 'updated', label: 'Updated' },
];
