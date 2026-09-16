import { describe, expect, it } from 'vitest';
import { isDroverLoadBalancer, loadBalancerDeleteConfirmation } from '../droverLoadBalancer';

describe('isDroverLoadBalancer', () => {
  it('returns true when both drover.managed=true and drover.resource_type=load_balancer tags are present', () => {
    expect(
      isDroverLoadBalancer({
        tags: ['drover.managed=true', 'drover.resource_type=load_balancer', 'env=prod'],
      }),
    ).toBe(true);
  });

  it('returns false when only one of the required tags is present', () => {
    expect(isDroverLoadBalancer({ tags: ['drover.managed=true'] })).toBe(false);
    expect(isDroverLoadBalancer({ tags: ['drover.resource_type=load_balancer'] })).toBe(false);
  });

  it('returns false when tags are empty, missing, or null', () => {
    expect(isDroverLoadBalancer({ tags: [] })).toBe(false);
    expect(isDroverLoadBalancer({ tags: null })).toBe(false);
    expect(isDroverLoadBalancer({})).toBe(false);
    expect(isDroverLoadBalancer(null)).toBe(false);
    expect(isDroverLoadBalancer(undefined)).toBe(false);
  });

  it('does not infer ownership from name or description', () => {
    expect(
      isDroverLoadBalancer({
        name: 'k3s-ha-example-deadbeef',
        description: 'Drover managed',
        tags: [],
      }),
    ).toBe(false);
  });

  it('requires explicit force deletion copy only for tagged Drover resources', () => {
    const protectedMessage = loadBalancerDeleteConfirmation(
      {
        name: 'control-plane',
        tags: ['drover.managed=true', 'drover.resource_type=load_balancer'],
      },
      'lb-1',
    );
    expect(protectedMessage).toContain('Drover가 관리하는');
    expect(protectedMessage).toContain('클러스터가 손상되거나');
    expect(protectedMessage).toContain('정말로 강제 삭제하시겠습니까?');

    const ordinaryMessage = loadBalancerDeleteConfirmation({ name: 'web', tags: [] }, 'lb-2');
    expect(ordinaryMessage).toContain('연결된 리스너/풀/멤버도 모두 삭제됩니다');
    expect(ordinaryMessage).not.toContain('강제 삭제');
  });
});
