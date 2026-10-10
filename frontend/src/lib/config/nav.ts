import type { BetaFeatures } from '$lib/stores/betaFeatures';
import { t } from '$lib/i18n/ns/nav';

type NavMessage = Parameters<typeof t>[0];

export const navIcons = {
  overview: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  instances: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2',
  image: 'M4 4h16v16H4zM4 16l5-5 4 4 3-3 4 4M14 8h.01',
  volume: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4',
  backup: 'M5 8a7 7 0 1 1-1 5M5 3v5H1M8 10v7h8v-7H8z',
  snapshot: 'M3 8h4l2-3h6l2 3h4v12H3V8zM15 13a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  folder: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z',
  network: 'M9 2h6v6H9zM2 16h6v6H2zM16 16h6v6h-6zM12 8v4M5 16v-4h14v4',
  shield: 'M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6l8-4z',
  cluster: 'M9 2h6v6H9zM2 16h6v6H2zM16 16h6v6h-6zM12 8v4M5 16v-4h14v4M9 16h6v6H9z',
  container: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
  database: 'M4 7c0-1.657 3.582-3 8-3s8 1.343 8 3M4 7v5c0 1.657 3.582 3 8 3s8-1.343 8-3V7M4 7c0 1.657 3.582 3 8 3s8-1.343 8-3M4 12v5c0 1.657 3.582 3 8 3s8-1.343 8-3v-5',
  bucket: 'M4 5h16l-2 16H6L4 5zM4 5a8 2 0 0 1 16 0M5 9h14',
  key: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z',
  chat: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z',
  audio: 'M4 10v4M8 6v12M12 3v18M16 6v12M20 10v4',
  floatingIp: 'M4 4h6v6H4zM14 14h6v6h-6zM14 4h6v6M20 4l-6 6M4 14v6h6M4 20l6-6',
  router: 'M5 14h14a2 2 0 0 1 2 2v4H3v-4a2 2 0 0 1 2-2zM8 17h.01M12 17h.01M12 3v11M8 7l4-4 4 4',
  balance: 'M9 2h6v6H9zM2 16h6v6H2zM16 16h6v6h-6zM12 8v4M5 16v-4h14v4M2 12h20',
  tunnel: 'M3 5h6v14H3zM15 5h6v14h-6zM7 12h10M10 9l-3 3 3 3M14 9l3 3-3 3',
  cpu: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z',
  templates: 'M4 3h16v18H4zM4 8h16M9 8v13M12 12h5M12 16h5',
  chart: 'M4 20V10h4v10H4zM10 20V4h4v16h-4zM16 20v-7h4v7h-4z',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 21v-2a8 8 0 0 1 16 0v2',
  users: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0',
  quota: 'M3 19a9 9 0 1 1 18 0M12 18l4-8M7 12h.01M12 9h.01M17 12h.01',
  sliders: 'M4 5h16M4 12h16M4 19h16M8 3v4M16 10v4M10 17v4',
  tools: 'M14 6a5 5 0 0 0-6 6l-5 5a3 3 0 0 0 4 4l5-5a5 5 0 0 0 6-6l-4 4-4-4 4-4z',
  layers: 'M12 3L3 8l9 5 9-5-9-5zM3 12l9 5 9-5M3 16l9 5 9-5',
  monitor: 'M3 3h18v14H3zM8 21h8M12 17v4M6 12l3-3 3 3 5-6',
  proxy: 'M3 7h18M17 3l4 4-4 4M21 17H3M7 13l-4 4 4 4',
  queue: 'M3 3h18v4H3zM3 10h18v4H3zM3 17h18v4H3z',
  cache: 'M3 5h18v14H3zM13 7l-4 5h4l-2 5 5-6h-4l1-4z',
  activity: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M12 7v5l3 3',
  orphan: 'M9 3h6v6H9zM3 15h6v6H3zM15 15h6v6h-6zM12 9v3M6 15v-3h3M15 12h3v3',
  document: 'M5 3h10l4 4v14H5V3zM15 3v5h4M8 12h8M8 16h8',
  announcement: 'M3 10h4l12-5v14l-12-5H3v-4zM7 14l2 7h4l-2-5',
  admin: 'M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6l8-4zM12 7l1.5 3 3.5.5-2.5 2.5.5 3.5-3-1.5-3 1.5.5-3.5L7 10.5l3.5-.5L12 7z',
} as const;

export interface NavItem {
  label: string;
  labelKey?: NavMessage;
  href: string;
  icon: string;
  service: string | null;
  beta?: keyof BetaFeatures;
  topLevel?: boolean;
}

export interface NavSection {
  label: string;
  labelKey?: NavMessage;
  prefix: string;
  extraPrefixes?: string[];
  icon: string;
  service?: string | null;
  beta?: keyof BetaFeatures;
  items: NavItem[];
}

/** Labels resolve when read, never at module initialization. Keep message keys for consumers. */
function withLabel<T extends object>(key: NavMessage, fields: T): T & { label: string; labelKey: NavMessage } {
  return Object.defineProperty({ ...fields, labelKey: key }, 'label', { enumerable: true, get: () => t(key) }) as T & { label: string; labelKey: NavMessage };
}

export const documentationNavItem: NavItem = withLabel('items.documentation', {
  href: '/docs', icon: navIcons.document, service: null, topLevel: true,
});

export const userNavSections: NavSection[] = [
  withLabel('sections.compute', {
    prefix: '/dashboard/compute',
    extraPrefixes: [],
    icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2',
    items: [
      withLabel('items.instances', { href: '/dashboard/compute/instances', icon: navIcons.instances, service: null }),
      withLabel('items.images', { href: '/dashboard/compute/images', icon: navIcons.image, service: null }),
    ],
  }),
  withLabel('sections.volumes', {
    prefix: '/dashboard/volumes',
    extraPrefixes: [],
    icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
    items: [
      withLabel('items.volumeList', { href: '/dashboard/volumes', icon: navIcons.volume, service: null }),
      withLabel('items.volumeBackups', { href: '/dashboard/volumes/backups', icon: navIcons.backup, service: null }),
      withLabel('items.volumeSnapshots', { href: '/dashboard/volumes/snapshots', icon: navIcons.snapshot, service: null, beta: 'volumeSnapshots' as const }),
    ],
  }),
  withLabel('sections.network', {
    prefix: '/dashboard/network',
    extraPrefixes: [],
    icon: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9',
    items: [
      withLabel('items.networks', { href: '/dashboard/network/networks', icon: navIcons.network, service: null }),
      withLabel('items.floatingIps', { href: '/dashboard/network/floating-ips', icon: navIcons.floatingIp, service: null }),
      withLabel('items.routers', { href: '/dashboard/network/routers', icon: navIcons.router, service: null }),
      withLabel('items.loadBalancers', { href: '/dashboard/network/loadbalancers', icon: navIcons.balance, service: null }),
      withLabel('items.securityGroups', { href: '/dashboard/network/security-groups', icon: navIcons.shield, service: null }),
      { label: 'Waygate', href: '/dashboard/network/waygate', icon: navIcons.tunnel, service: 'waygate' },
    ],
  }),
  withLabel('sections.fileStorage', {
    prefix: '/dashboard/file-storage',
    extraPrefixes: [],
    icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z',
    service: 'manila',
    items: [
      withLabel('items.fileStorage', { href: '/dashboard/file-storage', icon: navIcons.folder, service: null }),
      withLabel('items.fileStorageSnapshots', { href: '/dashboard/file-storage/snapshots', icon: navIcons.snapshot, service: null, beta: 'fileStorageSnapshots' as const }),
      withLabel('items.shareNetworks', { href: '/dashboard/file-storage/networks', icon: navIcons.network, service: null, beta: 'fileStorageShareNetworks' as const }),
      withLabel('items.securityServices', { href: '/dashboard/file-storage/security-services', icon: navIcons.shield, service: null, beta: 'fileStorageSecurityServices' as const }),
    ],
  }),
  {
    label: 'Palimpsest',
    prefix: '/palimpsest',
    icon: navIcons.layers,
    items: [
      withLabel('items.projectPackages', { href: '/palimpsest/packages', icon: navIcons.layers, service: null }),
    ],
  },
  withLabel('sections.containers', {
    prefix: '/dashboard/containers',
    extraPrefixes: ['/dashboard/drover'],
    icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
    service: 'containers',
    items: [
      withLabel('items.k8sClusters', { href: '/dashboard/containers/clusters', icon: navIcons.cluster, service: 'magnum' }),
      withLabel('items.containers', { href: '/dashboard/containers/instances', icon: navIcons.container, service: 'zun' }),
      { label: 'Drover', href: '/dashboard/drover', icon: navIcons.layers, service: 'k3s' },
    ],
  }),
  withLabel('sections.database', {
    prefix: '/dashboard/database',
    extraPrefixes: [],
    icon: 'M4 7c0-1.657 3.582-3 8-3s8 1.343 8 3M4 7v5c0 1.657 3.582 3 8 3s8-1.343 8-3V7M4 7c0 1.657 3.582 3 8 3s8-1.343 8-3M4 12v5c0 1.657 3.582 3 8 3s8-1.343 8-3v-5',
    service: 'trove',
    items: [
      withLabel('items.dbInstances', { href: '/dashboard/database/instances', icon: navIcons.database, service: null }),
      withLabel('items.dbBackups', { href: '/dashboard/database/backups', icon: navIcons.backup, service: null }),
    ],
  }),
  withLabel('sections.objectStorage', {
    prefix: '/dashboard/object-storage',
    extraPrefixes: [],
    icon: 'M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z',
    service: 'swift',
    items: [
      withLabel('items.buckets', { href: '/dashboard/object-storage/buckets', icon: navIcons.bucket, service: null }),
    ],
  }),
  withLabel('sections.keyManager', {
    prefix: '/dashboard/secrets',
    extraPrefixes: [],
    icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z',
    beta: 'keyManager' as const,
    items: [
      withLabel('items.secrets', { href: '/dashboard/secrets', icon: navIcons.key, service: null }),
    ],
  }),
  withLabel('sections.aiChat', {
    prefix: '/dashboard/chat',
    extraPrefixes: [],
    icon: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z',
    service: 'chat',
    items: [
      { label: 'Lumen', href: '/dashboard/chat', icon: navIcons.chat, service: 'chat' },
      withLabel('items.imageStudio', { href: '/dashboard/chat/images', icon: navIcons.image, service: 'chat' }),
      withLabel('items.audioStudio', { href: '/dashboard/chat/audio', icon: navIcons.audio, service: 'chat' })
    ],
  }),
];

export const adminNavSections: NavSection[] = [
  withLabel('sections.compute', {
    prefix: '/admin/instances',
    icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2',
    items: [
      withLabel('items.allInstances', { href: '/admin/instances', icon: navIcons.instances, service: null }),
      withLabel('items.flavors', { href: '/admin/flavors', icon: navIcons.cpu, service: null }),
      withLabel('items.images', { href: '/admin/images', icon: navIcons.image, service: null }),
      withLabel('items.hypervisors', { href: '/admin/hypervisors', icon: navIcons.monitor, service: null }),
    ],
  }),
  withLabel('sections.storage', {
    prefix: '/admin/volumes',
    icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
    items: [
      withLabel('items.allVolumes', { href: '/admin/volumes', icon: navIcons.volume, service: null }),
      withLabel('items.fileStorage', { href: '/admin/file-storage', icon: navIcons.folder, service: 'manila' }),
      withLabel('items.dbInstances', { href: '/admin/database-instances', icon: navIcons.database, service: 'trove' }),
      withLabel('items.objectStorage', { href: '/admin/object-storage', icon: navIcons.bucket, service: 'swift' }),
    ],
  }),
  withLabel('sections.network', {
    prefix: '/admin/topology',
    icon: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9',
    items: [
      withLabel('items.topology', { href: '/admin/topology', icon: navIcons.network, service: null }),
      withLabel('items.networks', { href: '/admin/networks', icon: navIcons.layers, service: null }),
      withLabel('items.floatingIps', { href: '/admin/floating-ips', icon: navIcons.floatingIp, service: null }),
      withLabel('items.routers', { href: '/admin/routers', icon: navIcons.router, service: null }),
      withLabel('items.loadBalancers', { href: '/admin/loadbalancers', icon: navIcons.balance, service: null }),
      withLabel('items.ports', { href: '/admin/ports', icon: navIcons.cpu, service: null }),
      { label: 'Waygate', href: '/admin/waygate', icon: navIcons.tunnel, service: 'waygate' },
    ],
  }),
  withLabel('sections.containers', {
    prefix: '/admin/containers',
    icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
    items: [
      withLabel('items.allContainers', { href: '/admin/containers', icon: navIcons.container, service: 'zun' }),
      { label: 'Drover', href: '/admin/drover', icon: navIcons.layers, service: 'k3s' },
      withLabel('items.clusterTemplates', { href: '/admin/drover/templates', icon: navIcons.templates, service: 'k3s' }),
    ],
  }),
  {
    label: 'Lumen',
    prefix: '/admin/chat',
    icon: 'M8 10h8M8 14h5M21 12a9 9 0 01-9 9H3l2.4-4.8A9 9 0 1121 12z',
    items: [
      { label: 'Lumen', href: '/admin/chat', icon: navIcons.chat, service: 'chat' },
      withLabel('items.chatStats', { href: '/admin/chat/stats', icon: navIcons.chart, service: 'chat' }),
      withLabel('items.userQuotas', { href: '/admin/chat/quotas', icon: navIcons.quota, service: 'chat' }),
      withLabel('items.modelSettings', { href: '/admin/chat/models', icon: navIcons.sliders, service: 'chat' }),
      withLabel('items.toolSettings', { href: '/admin/chat/tools', icon: navIcons.tools, service: 'chat' }),
    ],
  },
  {
    label: 'Palimpsest',
    prefix: '/admin/libraries',
    icon: 'M12 3L3 8l9 5 9-5-9-5zM3 12l9 5 9-5M3 16l9 5 9-5',
    items: [
      { label: 'Palimpsest', href: '/admin/libraries', icon: navIcons.layers, service: null, topLevel: true },
    ],
  },
  withLabel('sections.keyManager', {
    prefix: '/admin/secrets',
    icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z',
    beta: 'keyManager' as const,
    items: [
      withLabel('items.projectQuotas', { href: '/admin/secrets', icon: navIcons.key, service: null }),
    ],
  }),
  withLabel('sections.monitoring', {
    prefix: '/admin/monitoring',
    icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
    items: [
      withLabel('items.monitoringOverview', { href: '/admin/monitoring', icon: navIcons.monitor, service: null }),
      withLabel('items.nodes', { href: '/admin/monitoring/node', icon: navIcons.instances, service: null }),
      { label: 'MySQL', href: '/admin/monitoring/mysql', icon: navIcons.database, service: null },
      { label: 'ProxySQL', href: '/admin/monitoring/proxysql', icon: navIcons.proxy, service: null },
      { label: 'HAProxy', href: '/admin/monitoring/haproxy', icon: navIcons.balance, service: null },
      { label: 'RabbitMQ', href: '/admin/monitoring/rabbitmq', icon: navIcons.queue, service: null },
      { label: 'Memcached', href: '/admin/monitoring/memcached', icon: navIcons.cache, service: null },
      { label: 'etcd', href: '/admin/monitoring/etcd', icon: navIcons.key, service: null },
      { label: 'Libvirt', href: '/admin/monitoring/libvirt', icon: navIcons.cpu, service: null },
      { label: 'OpenStack', href: '/admin/monitoring/openstack', icon: navIcons.layers, service: null },
      { label: 'Ceph', href: '/admin/monitoring/ceph', icon: navIcons.volume, service: null },
    ],
  }),
  withLabel('sections.system', {
    prefix: '/admin/services',
    icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z',
    items: [
      withLabel('items.serviceStatus', { href: '/admin/services', icon: navIcons.cpu, service: null }),
      withLabel('items.events', { href: '/admin/events', icon: navIcons.activity, service: null }),
      withLabel('items.orphans', { href: '/admin/orphans', icon: navIcons.orphan, service: null }),
      withLabel('items.notion', { href: '/admin/notion', icon: navIcons.document, service: null }),
      withLabel('items.announcements', { href: '/admin/announcements', icon: navIcons.announcement, service: null }),
      withLabel('items.settings', { href: '/admin/settings', icon: navIcons.sliders, service: null }),
    ],
  }),
  withLabel('sections.identity', {
    prefix: '/admin/users',
    icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z',
    items: [
      withLabel('items.users', { href: '/admin/users', icon: navIcons.user, service: null }),
      withLabel('items.projects', { href: '/admin/projects', icon: navIcons.folder, service: null }),
      withLabel('items.quotas', { href: '/admin/quotas', icon: navIcons.quota, service: null }),
      withLabel('items.groups', { href: '/admin/groups', icon: navIcons.users, service: null }),
      withLabel('items.roles', { href: '/admin/roles', icon: navIcons.shield, service: null }),
      withLabel('items.systemAdmins', { href: '/admin/system-admins', icon: navIcons.admin, service: null }),
    ],
  }),
];

export function isNavSectionActive(section: NavSection, pathname: string): boolean {
  const matches = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  return matches(section.prefix) || section.extraPrefixes?.some(matches) === true || section.items.some((item) => matches(item.href));
}

export function allNavItems(isAdmin: boolean, betaFeatures: BetaFeatures): Array<NavItem & { section: string; sectionKey?: NavMessage }> {
  const sections = isAdmin ? adminNavSections : userNavSections;
  const overview = isAdmin ? [{ label: t('items.overview'), labelKey: 'items.overview' as const, href: '/admin', icon: navIcons.overview, service: null, section: t('sections.overview'), sectionKey: 'sections.overview' as const }] : [];
  return [...overview, { ...documentationNavItem, section: t('sections.documentation'), sectionKey: 'sections.documentation' as const }, ...sections.flatMap((section) => {
    if (section.beta && !betaFeatures[section.beta]) return [];
    return section.items
      .filter((item) => !item.beta || betaFeatures[item.beta])
      .map((item) => ({ ...item, service: item.service ?? section.service ?? null, section: section.label, sectionKey: section.labelKey }));
  })];
}
