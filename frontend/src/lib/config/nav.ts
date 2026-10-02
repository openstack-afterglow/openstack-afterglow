import type { BetaFeatures } from '$lib/stores/betaFeatures';
import { t } from '$lib/i18n/ns/nav';

export interface NavItem {
  label: string;
  href: string;
  service: string | null;
  beta?: keyof BetaFeatures;
  topLevel?: boolean;
}

export interface NavSection {
  label: string;
  prefix: string;
  extraPrefixes?: string[];
  icon: string;
  service?: string | null;
  beta?: keyof BetaFeatures;
  items: NavItem[];
}

type NavMessage = Parameters<typeof t>[0];

/**
 * Adds a `label` getter so module-level navigation follows the active language on every read.
 * Spreading the result copies the label of that moment, which is why callers spread only inside
 * reactive computations such as `allNavItems`.
 */
function withLabel<T extends object>(key: NavMessage, fields: T): T & { label: string } {
  return Object.defineProperty({ ...fields }, 'label', { enumerable: true, get: () => t(key) }) as T & { label: string };
}

export const userNavSections: NavSection[] = [
  withLabel('sections.compute', {
    prefix: '/dashboard/compute',
    extraPrefixes: [],
    icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2',
    items: [
      withLabel('items.instances', { href: '/dashboard/compute/instances', service: null }),
      withLabel('items.images', { href: '/dashboard/compute/images', service: null }),
    ],
  }),
  withLabel('sections.volumes', {
    prefix: '/dashboard/volumes',
    extraPrefixes: [],
    icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
    items: [
      withLabel('items.volumeList', { href: '/dashboard/volumes', service: null }),
      withLabel('items.volumeBackups', { href: '/dashboard/volumes/backups', service: null }),
      withLabel('items.volumeSnapshots', { href: '/dashboard/volumes/snapshots', service: null, beta: 'volumeSnapshots' as const }),
    ],
  }),
  withLabel('sections.fileStorage', {
    prefix: '/dashboard/file-storage',
    extraPrefixes: [],
    icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z',
    service: 'manila',
    items: [
      withLabel('items.fileStorage', { href: '/dashboard/file-storage', service: null }),
      withLabel('items.fileStorageSnapshots', { href: '/dashboard/file-storage/snapshots', service: null, beta: 'fileStorageSnapshots' as const }),
      withLabel('items.shareNetworks', { href: '/dashboard/file-storage/networks', service: null, beta: 'fileStorageShareNetworks' as const }),
      withLabel('items.securityServices', { href: '/dashboard/file-storage/security-services', service: null, beta: 'fileStorageSecurityServices' as const }),
    ],
  }),
  withLabel('sections.containers', {
    prefix: '/dashboard/containers',
    extraPrefixes: ['/dashboard/drover'],
    icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
    service: 'containers',
    items: [
      withLabel('items.k8sClusters', { href: '/dashboard/containers/clusters', service: 'magnum' }),
      withLabel('items.containers', { href: '/dashboard/containers/instances', service: 'zun' }),
      { label: 'Drover', href: '/dashboard/drover', service: 'k3s' },
    ],
  }),
  withLabel('sections.database', {
    prefix: '/dashboard/database',
    extraPrefixes: [],
    icon: 'M4 7c0-1.657 3.582-3 8-3s8 1.343 8 3M4 7v5c0 1.657 3.582 3 8 3s8-1.343 8-3V7M4 7c0 1.657 3.582 3 8 3s8-1.343 8-3M4 12v5c0 1.657 3.582 3 8 3s8-1.343 8-3v-5',
    service: 'trove',
    items: [
      withLabel('items.dbInstances', { href: '/dashboard/database/instances', service: null }),
      withLabel('items.dbBackups', { href: '/dashboard/database/backups', service: null }),
    ],
  }),
  withLabel('sections.objectStorage', {
    prefix: '/dashboard/object-storage',
    extraPrefixes: [],
    icon: 'M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z',
    service: 'swift',
    items: [
      withLabel('items.buckets', { href: '/dashboard/object-storage/buckets', service: null }),
    ],
  }),
  withLabel('sections.keyManager', {
    prefix: '/dashboard/secrets',
    extraPrefixes: [],
    icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z',
    beta: 'keyManager' as const,
    items: [
      withLabel('items.secrets', { href: '/dashboard/secrets', service: null }),
    ],
  }),
  withLabel('sections.aiChat', {
    prefix: '/dashboard/chat',
    extraPrefixes: [],
    icon: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z',
    service: 'chat',
    items: [
      { label: 'Lumen', href: '/dashboard/chat', service: 'chat' },
      withLabel('items.imageStudio', { href: '/dashboard/chat/images', service: 'chat' }),
      withLabel('items.audioStudio', { href: '/dashboard/chat/audio', service: 'chat' }),
    ],
  }),
  withLabel('sections.network', {
    prefix: '/dashboard/network',
    extraPrefixes: [],
    icon: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9',
    items: [
      withLabel('items.networks', { href: '/dashboard/network/networks', service: null }),
      withLabel('items.floatingIps', { href: '/dashboard/network/floating-ips', service: null }),
      withLabel('items.routers', { href: '/dashboard/network/routers', service: null }),
      withLabel('items.loadBalancers', { href: '/dashboard/network/loadbalancers', service: null }),
      withLabel('items.securityGroups', { href: '/dashboard/network/security-groups', service: null }),
      { label: 'Waygate', href: '/dashboard/network/waygate', service: 'waygate' },
    ],
  }),
];

export const adminNavSections: NavSection[] = [
  withLabel('sections.compute', {
    prefix: '/admin/instances',
    icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2',
    items: [
      withLabel('items.allInstances', { href: '/admin/instances', service: null }),
      withLabel('items.flavors', { href: '/admin/flavors', service: null }),
      withLabel('items.images', { href: '/admin/images', service: null }),
      withLabel('items.hypervisors', { href: '/admin/hypervisors', service: null }),
    ],
  }),
  withLabel('sections.storage', {
    prefix: '/admin/volumes',
    icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
    items: [
      withLabel('items.allVolumes', { href: '/admin/volumes', service: null }),
      withLabel('items.fileStorage', { href: '/admin/file-storage', service: 'manila' }),
      withLabel('items.dbInstances', { href: '/admin/database-instances', service: 'trove' }),
      withLabel('items.objectStorage', { href: '/admin/object-storage', service: 'swift' }),
    ],
  }),
  withLabel('sections.network', {
    prefix: '/admin/topology',
    icon: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9',
    items: [
      withLabel('items.topology', { href: '/admin/topology', service: null }),
      withLabel('items.networks', { href: '/admin/networks', service: null }),
      withLabel('items.floatingIps', { href: '/admin/floating-ips', service: null }),
      withLabel('items.routers', { href: '/admin/routers', service: null }),
      withLabel('items.loadBalancers', { href: '/admin/loadbalancers', service: null }),
      withLabel('items.ports', { href: '/admin/ports', service: null }),
    ],
  }),
  withLabel('sections.containers', {
    prefix: '/admin/containers',
    icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
    items: [
      withLabel('items.allContainers', { href: '/admin/containers', service: 'zun' }),
    ],
  }),
  withLabel('sections.services', {
    prefix: '/admin/drover',
    icon: 'M4 7h16M4 12h16M4 17h16',
    items: [
      { label: 'Drover', href: '/admin/drover', service: 'k3s', topLevel: true },
      { label: 'Lumen', href: '/admin/chat', service: 'chat', topLevel: true },
      { label: 'Palimpsest', href: '/admin/libraries', service: null, topLevel: true },
      { label: 'Waygate', href: '/admin/waygate', service: 'waygate', topLevel: true },
      withLabel('items.clusterTemplates', { href: '/admin/drover/templates', service: 'k3s' }),
      withLabel('items.chatStats', { href: '/admin/chat/stats', service: 'chat' }),
      withLabel('items.userQuotas', { href: '/admin/chat/quotas', service: 'chat' }),
      withLabel('items.modelSettings', { href: '/admin/chat/models', service: 'chat' }),
      withLabel('items.toolSettings', { href: '/admin/chat/tools', service: 'chat' }),
    ],
  }),
  withLabel('sections.keyManager', {
    prefix: '/admin/secrets',
    icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z',
    beta: 'keyManager' as const,
    items: [
      withLabel('items.projectQuotas', { href: '/admin/secrets', service: null }),
    ],
  }),
  withLabel('sections.monitoring', {
    prefix: '/admin/monitoring',
    icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
    items: [
      withLabel('items.monitoringOverview', { href: '/admin/monitoring', service: null }),
      withLabel('items.nodes', { href: '/admin/monitoring/node', service: null }),
      { label: 'MySQL', href: '/admin/monitoring/mysql', service: null },
      { label: 'HAProxy', href: '/admin/monitoring/haproxy', service: null },
      { label: 'RabbitMQ', href: '/admin/monitoring/rabbitmq', service: null },
      { label: 'Memcached', href: '/admin/monitoring/memcached', service: null },
      { label: 'etcd', href: '/admin/monitoring/etcd', service: null },
      { label: 'Libvirt', href: '/admin/monitoring/libvirt', service: null },
      { label: 'OpenStack', href: '/admin/monitoring/openstack', service: null },
      { label: 'Ceph', href: '/admin/monitoring/ceph', service: null },
    ],
  }),
  withLabel('sections.system', {
    prefix: '/admin/services',
    icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z',
    items: [
      withLabel('items.serviceStatus', { href: '/admin/services', service: null }),
      withLabel('items.events', { href: '/admin/events', service: null }),
      withLabel('items.orphans', { href: '/admin/orphans', service: null }),
      withLabel('items.notion', { href: '/admin/notion', service: null }),
      withLabel('items.announcements', { href: '/admin/announcements', service: null }),
      withLabel('items.settings', { href: '/admin/settings', service: null }),
    ],
  }),
  withLabel('sections.identity', {
    prefix: '/admin/users',
    icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z',
    items: [
      withLabel('items.users', { href: '/admin/users', service: null }),
      withLabel('items.projects', { href: '/admin/projects', service: null }),
      withLabel('items.quotas', { href: '/admin/quotas', service: null }),
      withLabel('items.groups', { href: '/admin/groups', service: null }),
      withLabel('items.roles', { href: '/admin/roles', service: null }),
      withLabel('items.systemAdmins', { href: '/admin/system-admins', service: null }),
    ],
  }),
];

export function isNavSectionActive(section: NavSection, pathname: string): boolean {
  const matches = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  return matches(section.prefix) || section.extraPrefixes?.some(matches) === true || section.items.some((item) => matches(item.href));
}

export function allNavItems(isAdmin: boolean, betaFeatures: BetaFeatures): Array<NavItem & { section: string }> {
  const sections = isAdmin ? adminNavSections : userNavSections;
  const overview = isAdmin ? [{ label: t('items.overview'), href: '/admin', service: null, section: t('sections.overview') }] : [];
  return [...overview, ...sections.flatMap((section) => {
    if (section.beta && !betaFeatures[section.beta]) return [];
    return section.items
      .filter((item) => !item.beta || betaFeatures[item.beta])
      .map((item) => ({ ...item, service: item.service ?? section.service ?? null, section: section.label }));
  })];
}
