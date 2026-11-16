import { t } from '$lib/i18n/ns/volume';

/** Policy controls share behavior; snapshot copy must never promise full backups. */
export function recoveryPolicyText(resource: 'backup' | 'snapshot', key: Parameters<typeof t>[0], params?: Parameters<typeof t>[1]): string {
 if (resource === 'snapshot' && key === 'backupPolicy.description') return t('snapshotGroups.policy.description', params);
 if (resource === 'snapshot' && key === 'backupPolicy.calendarHelp') return t('snapshotGroups.policy.calendarHelp', params);
 return t((resource === 'snapshot' && key.startsWith('autoPolicy.') ? key.replace('autoPolicy.', 'snapshotGroups.policy.') : key) as Parameters<typeof t>[0], params);
}
