import { t } from '$lib/i18n/ns/drover-pages';

export interface HasTags {
  tags?: readonly string[] | null;
  name?: string | null;
  description?: string | null;
}

export function isDroverLoadBalancer(item: HasTags | null | undefined): boolean {
  if (!Array.isArray(item?.tags)) return false;
  return item.tags.includes('drover.managed=true') && item.tags.includes('drover.resource_type=load_balancer');
}

export function loadBalancerDeleteConfirmation(item: HasTags | null | undefined, id: string): string {
  const name = item?.name || id;
  if (!isDroverLoadBalancer(item)) {
    return t('loadBalancer.deleteConfirmation', { name });
  }
  return t('loadBalancer.forceDeleteConfirmation', { name });
}
