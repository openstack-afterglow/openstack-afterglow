// Afterglow route label map
// URL path segment → localized display label or product name.
// Fallback page titles for contextual navigation on undeclared routes.

import { t } from '$lib/i18n/ns/nav';

type NavMessage = Parameters<typeof t>[0];

/** Resolve translated segments at call time to follow the active language. */
const ROUTE_LABEL_KEYS: Record<string, NavMessage> = {
  // Top level
  dashboard: 'routes.dashboard',
  admin: 'routes.admin',

  // Overview
  'my-resources': 'routes.myResources',
  notifications: 'routes.notifications',

  // Compute
  compute: 'routes.compute',
  instances: 'routes.instances',
  keypairs: 'routes.keypairs',
  images: 'routes.images',
  flavors: 'routes.flavors',
  hypervisors: 'routes.hypervisors',

  // Volumes
  volumes: 'routes.volumes',
  backups: 'routes.backups',
  snapshots: 'routes.snapshots',

  // File Storage
  'file-storage': 'routes.fileStorage',
  manage: 'routes.manage',
  networks: 'routes.networks',
  'security-services': 'routes.securityServices',

  // Containers
  containers: 'routes.containers',
  clusters: 'routes.clusters',

  // Database
  database: 'routes.database',

  // Object Storage
  'object-storage': 'routes.objectStorage',
  buckets: 'routes.buckets',
  audio: 'routes.audio',

  // Network
  network: 'routes.network',
  routers: 'routes.routers',
  'security-groups': 'routes.securityGroups',
  loadbalancers: 'routes.loadbalancers',
  topology: 'routes.topology',
  'floating-ips': 'routes.floatingIps',
  ports: 'routes.ports',

  // Library (Union Mount)
  library: 'routes.library',
  libraries: 'routes.libraries',
  templates: 'routes.templates',
  packages: 'routes.projectPackages',

  // Project settings
  'project-settings': 'routes.projectSettings',
  invitations: 'routes.invitations',

  // Admin
  monitoring: 'routes.monitoring',
  services: 'routes.services',
  notion: 'routes.notion',
  settings: 'routes.settings',
  users: 'routes.users',
  projects: 'routes.projects',
  quotas: 'routes.quotas',
  groups: 'routes.groups',
  roles: 'routes.roles',
  announcements: 'routes.announcements',
};

/** Product and protocol names are never translated. */
const ROUTE_PRODUCT_LABELS: Record<string, string> = {
  gpu: 'GPU',
  k3s: 'Drover',
  chat: 'Lumen',
  waygate: 'Waygate',
  palimpsest: 'Palimpsest',
};

function routeLabel(segment: string): string | undefined {
  const key = ROUTE_LABEL_KEYS[segment];
  return key ? t(key) : ROUTE_PRODUCT_LABELS[segment];
}

/** Derives the page title while excluding resource UUIDs and creation routes. */
export function derivePageTitle(pathname: string): string {
  // Strip leading slash and split
  const parts = pathname.replace(/^\//, '').split('/').filter(Boolean);

  // Strip the root mode segment (dashboard / admin)
  const relevant = parts.slice(1).filter(p => !isUuid(p) && p !== 'new');

  const last = relevant.at(-1) ?? parts[0] ?? '';
  return routeLabel(last) ?? last;
}

function isUuid(s: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s) ||
    // also catch shorter hex-like IDs
    /^[0-9a-f]{32}$/i.test(s);
}
