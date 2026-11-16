import type { RecoveryPointIdentity, Volume, VolumeBackup } from '$lib/types/volume';
import type { VolumeBackupPolicy } from '$lib/types/volumeBackupPolicy';
import { t } from '$lib/i18n/ns/volume';

export interface RecoveryPoint extends RecoveryPointIdentity {
 id: string; volume_id: string; created_at: string | null;
}
export interface RecoveryGroup {
 id: string;
 volume: Volume | null;
 points: RecoveryPoint[];
 latest: string | null;
 policy: VolumeBackupPolicy | null;
}
export function groupRecoveryPoints(volumes: Volume[], points: RecoveryPoint[], policies: VolumeBackupPolicy[] = []): RecoveryGroup[] {
 const groups = new Map<string, RecoveryGroup>();
 const ensure = (id: string) => {
  let group = groups.get(id);
  if (!group) { group = { id, volume: null, points: [], latest: null, policy: null }; groups.set(id, group); }
  return group;
 };
 for (const volume of volumes) ensure(volume.id).volume = volume;
 for (const policy of policies) ensure(policy.volume_id).policy = policy;
 for (const point of points) ensure(point.volume_id).points.push(point);
 for (const group of groups.values()) {
  group.points.sort((a, b) => (Date.parse(b.created_at ?? '') || 0) - (Date.parse(a.created_at ?? '') || 0));
  group.latest = group.points.find(point => Number.isFinite(Date.parse(point.created_at ?? '')))?.created_at ?? null;
 }
 return [...groups.values()];
}
// The list shows only volumes that already have a recovery point. The complete group set is kept for detail
// views, so `?volume=` and the volume list's auto-policy link still open any volume, including policy-only ones.
export function listedRecoveryGroups(groups: RecoveryGroup[]): RecoveryGroup[] {
 return groups.filter(group => group.points.length > 0);
}
export function recoveryVolumeName(group: RecoveryGroup, inventoryKnown = true): string {
 return group.volume?.name || (group.volume ? group.id.slice(0, 8) : t(inventoryKnown ? 'backupGroups.deletedVolume' : 'backupGroups.unknownVolume', { id: group.id.slice(0, 8) }));
}
export function recoveryOrigin(point: RecoveryPointIdentity): string {
 return point.origin === 'auto' && point.auto_tier ? t('backupGroups.automaticTier', { tier: t(`autoPolicy.tier.${point.auto_tier}`) }) : t('backupGroups.manual');
}
export function recoveryCreator(point: RecoveryPointIdentity, userId: string | null, names: Record<string, string> = {}): string {
 if (point.origin === 'auto') return recoveryOrigin(point);
 if (!point.user_id) return t('backupGroups.unknownCreator');
 return point.user_id === userId ? t('backupGroups.me') : names[point.user_id] || point.user_id.slice(0, 8);
}
export function hasFullBackup(backups: VolumeBackup[], volumeId: string): boolean {
 return backups.some(point => point.volume_id === volumeId && point.status === 'available' && point.is_incremental === false);
}
export function recoveryVolumeUrl(url: URL, volumeId: string | null): URL {
 const next = new URL(url);
 next.searchParams.delete('auto-backup');
 if (volumeId) next.searchParams.set('volume', volumeId); else next.searchParams.delete('volume');
 return next;
}
