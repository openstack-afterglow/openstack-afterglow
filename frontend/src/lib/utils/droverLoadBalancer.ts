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
    return `로드밸런서 "${name}"을 삭제하시겠습니까? (연결된 리스너/풀/멤버도 모두 삭제됩니다)`;
  }
  return `[강제 삭제 경고] 로드밸런서 "${name}"은 Drover가 관리하는 클러스터 리소스입니다.\n강제 삭제 시 K3s 클러스터가 손상되거나 서비스가 중단될 수 있습니다.\nDrover에서 클러스터를 삭제하거나 구성을 변경하는 것을 권장합니다.\n\n정말로 강제 삭제하시겠습니까?`;
}
