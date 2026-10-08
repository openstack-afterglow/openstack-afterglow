import { derived } from 'svelte/store';
import { serviceCapabilities } from './servicePermissions';

export type KubeconfigGrade = 'user' | 'editor' | 'admin';

// Native endpoints enforce each explicitly requested credential grade; the UI never synthesizes one.
// Routine downloads use expiring, revocable TokenRequest grades; the stored full certificate (`admin`)
// cannot be recalled once downloaded, so it is only requested through a separate confirmed action.
export const k3sPermissions = derived(serviceCapabilities, (can) => {
  const adminCredentials = can('drover-access_admin');
  const workloads = can('drover-workloads_editor') || adminCredentials;
  const kubeconfigGrade: KubeconfigGrade | null = can('drover-workloads_editor')
    ? 'editor'
    : can('drover-access_user') || adminCredentials ? 'user' : null;
  return {
    inventory: can('drover-inventory_reader'),
    editClusters: can('drover-clusters_editor'),
    administerClusters: can('drover-clusters_admin'),
    adminCredentials,
    credentials: kubeconfigGrade !== null,
    kubeconfigGrade,
    workloads,
  };
});
