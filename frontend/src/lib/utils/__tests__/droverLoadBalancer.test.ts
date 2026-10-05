// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { isDroverLoadBalancer } from '../droverLoadBalancer';

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
});
