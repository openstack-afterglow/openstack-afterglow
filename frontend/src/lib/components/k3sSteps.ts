import { t } from '$lib/i18n/ns/drover';
import { PROVISION_ICON } from '$lib/components/wizard/provisionIcons';
import type { StepProgressStatus } from '$lib/components/ui';

export interface K3sStep {
  id: string;
  label: string;
  /** Pipeline icon path data on a 24×24 stroke grid. */
  icon: string;
}

export const K3S_CREATE_STEPS: K3sStep[] = [
  { id: 'security_group',   get label() { return t('steps.securityGroup'); }, icon: PROVISION_ICON.shield },
  { id: 'server_volume',    get label() { return t('steps.serverVolume'); }, icon: PROVISION_ICON.disk },
  { id: 'server_creating',  get label() { return t('steps.serverVm'); }, icon: PROVISION_ICON.server },
  { id: 'waiting_callback', get label() { return t('steps.initialize'); }, icon: PROVISION_ICON.terminal },
  { id: 'completed',        get label() { return t('steps.completed'); }, icon: PROVISION_ICON.checkCircle },
];

export const K3S_DELETE_STEPS: K3sStep[] = [
  { id: 'delete_init',           get label() { return t('steps.prepare'); }, icon: PROVISION_ICON.clipboard },
  { id: 'delete_lb_cleanup',     get label() { return t('steps.cleanupLb'); }, icon: PROVISION_ICON.balancer },
  { id: 'delete_app_credential', get label() { return t('steps.appCredential'); }, icon: PROVISION_ICON.key },
  { id: 'delete_k8s_nodes',      get label() { return t('steps.k8sNodes'); }, icon: PROVISION_ICON.nodes },
  { id: 'delete_agent_vms',      get label() { return t('steps.agentVm'); }, icon: PROVISION_ICON.servers },
  { id: 'delete_server_vm',      get label() { return t('steps.serverVm'); }, icon: PROVISION_ICON.server },
  { id: 'delete_security_group', get label() { return t('steps.securityGroup'); }, icon: PROVISION_ICON.shield },
  { id: 'delete_record',         get label() { return t('steps.recordHistory'); }, icon: PROVISION_ICON.archive },
  { id: 'completed',             get label() { return t('steps.completed'); }, icon: PROVISION_ICON.checkCircle },
];

/**
 * A failure is attributed to the last step the stream reported that belongs to the active stage list.
 * HA/rotation substeps not shown by this view do not erase the last represented stage.
 */
export function k3sProgressState(
  step: string,
  stepTimings: Record<string, number>,
  activeSteps: readonly K3sStep[],
): { current: string | null; status: StepProgressStatus } {
  if (step === 'completed') return { current: step, status: 'done' };
  if (step === 'failed') {
    const reached = Object.keys(stepTimings).filter((id) => id !== 'failed' && id !== 'completed' && activeSteps.some((stage) => stage.id === id));
    return { current: reached.at(-1) ?? null, status: 'failed' };
  }
  return { current: step || null, status: 'running' };
}
