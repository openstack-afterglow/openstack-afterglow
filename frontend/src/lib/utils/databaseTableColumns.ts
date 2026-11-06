import { t } from '$lib/i18n/ns/database';
import type { DbBackup, DbDatabase, DbInstance, DbUser } from '$lib/types/database';
import type { TableColumn } from './tableView.svelte';

export function dbInstanceColumns(): TableColumn<DbInstance>[] {
	return [
		{ key: 'name', label: t('labels.name'), value: (row) => row.name },
		{ key: 'status', label: t('labels.status'), value: (row) => row.status },
		{ key: 'datastore', label: t('labels.datastoreEnglish'), value: (row) => [row.datastore?.type, row.datastore?.version].filter(Boolean).join(' ') || undefined },
		{ key: 'size', label: t('labels.sizeGb'), value: (row) => row.size },
		{ key: 'created', label: t('labels.created'), value: (row) => row.created_at || undefined, filterValues: (row) => [row.created_at?.slice(0, 10) || undefined], format: (value) => String(value).slice(0, 10) },
	];
}

export function dbBackupColumns(instances?: readonly DbInstance[]): TableColumn<DbBackup>[] {
	return [
		{ key: 'name', label: t('labels.name'), value: (row) => row.name || row.id },
		{ key: 'status', label: t('labels.status'), value: (row) => row.status },
		...(instances ? [
			{ key: 'source', label: t('backups.source'), value: (row: DbBackup) => instances.find((instance) => instance.id === row.instance_id)?.name ?? (row.instance_id ? t('backups.sourceDeleted') : undefined) },
			{ key: 'datastore', label: t('labels.datastoreEnglish'), value: (row: DbBackup) => [row.datastore?.type, row.datastore?.version].filter(Boolean).join(' ') || undefined },
		] : []),
		{ key: 'size', label: t('labels.size'), value: (row) => row.size },
		{ key: 'created', label: t('labels.created'), value: (row) => row.created_at || undefined, filterValues: (row) => [row.created_at?.slice(0, 10) || undefined], format: (value) => String(value).slice(0, 10) },
	];
}

export function dbUserColumns(): TableColumn<DbUser>[] {
	return [
		{ key: 'name', label: t('labels.username'), value: (row) => row.name },
		{ key: 'host', label: t('labels.host'), value: (row) => row.host || '%' },
		{ key: 'databases', label: t('labels.databases'), value: (row) => row.databases?.map((database) => database.name).join(', ') || undefined, filterValues: (row) => row.databases?.map((database) => database.name) ?? [] },
	];
}

export function dbDatabaseColumns(): TableColumn<DbDatabase>[] {
	return [{ key: 'name', label: t('labels.name'), value: (row) => row.name }];
}
