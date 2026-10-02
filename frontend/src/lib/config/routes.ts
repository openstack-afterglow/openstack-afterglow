// Afterglow route label map
// URL path segment → localized display label (nav catalog) or a product name
// Used to auto-derive the header breadcrumb from $page.url.pathname

import { t } from '$lib/i18n/ns/nav';

type NavMessage = Parameters<typeof t>[0];

/** Translated segments; resolved at call time so the breadcrumb follows the active language. */
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
};

function routeLabel(segment: string): string | undefined {
  const key = ROUTE_LABEL_KEYS[segment];
  return key ? t(key) : ROUTE_PRODUCT_LABELS[segment];
}

interface BreadcrumbResult {
  /** Short parent path, e.g. "COMPUTE / INSTANCES" */
  breadcrumb: string;
  /** Page title, e.g. "인스턴스" */
  title: string;
}

/**
 * Derives breadcrumb display strings from a URL pathname.
 * /dashboard/compute/instances → { breadcrumb: 'COMPUTE', title: '인스턴스' }
 */
export function deriveBreadcrumb(pathname: string): BreadcrumbResult {
  // Strip leading slash and split
  const parts = pathname.replace(/^\//, '').split('/').filter(Boolean);

  // Strip the root mode segment (dashboard / admin)
  const relevant = parts.slice(1).filter(p => !isUuid(p) && p !== 'new');

  if (relevant.length === 0) {
    // /dashboard 또는 /admin 루트인 경우 첫 세그먼트로 타이틀 결정
    const root = parts[0];
    return { breadcrumb: '', title: routeLabel(root) ?? root };
  }

  const labels = relevant.map(p => (routeLabel(p) ?? p).toUpperCase());

  return {
    breadcrumb: labels.slice(0, -1).join(' / '),
    title: routeLabel(relevant[relevant.length - 1]) ?? relevant[relevant.length - 1],
  };
}

function isUuid(s: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s) ||
    // also catch shorter hex-like IDs
    /^[0-9a-f]{32}$/i.test(s);
}
