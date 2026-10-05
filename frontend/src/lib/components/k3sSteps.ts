import { t } from '$lib/i18n/ns/drover';

export const K3S_CREATE_STEPS = [
  { id: 'security_group',   get label() { return t('steps.securityGroup'); } },
  { id: 'server_volume',    get label() { return t('steps.serverVolume'); } },
  { id: 'server_creating',  get label() { return t('steps.serverVm'); } },
  { id: 'waiting_callback', get label() { return t('steps.initialize'); } },
  { id: 'completed',        get label() { return t('steps.completed'); } },
];

export const K3S_DELETE_STEPS = [
  { id: 'delete_init',           get label() { return t('steps.prepare'); } },
  { id: 'delete_lb_cleanup',     get label() { return t('steps.cleanupLb'); } },
  { id: 'delete_app_credential', get label() { return t('steps.appCredential'); } },
  { id: 'delete_k8s_nodes',      get label() { return t('steps.k8sNodes'); } },
  { id: 'delete_agent_vms',      get label() { return t('steps.agentVm'); } },
  { id: 'delete_server_vm',      get label() { return t('steps.serverVm'); } },
  { id: 'delete_security_group', get label() { return t('steps.securityGroup'); } },
  { id: 'delete_record',         get label() { return t('steps.recordHistory'); } },
  { id: 'completed',             get label() { return t('steps.completed'); } },
];
