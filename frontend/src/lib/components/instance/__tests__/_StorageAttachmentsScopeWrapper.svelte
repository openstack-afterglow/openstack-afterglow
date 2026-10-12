<script lang="ts">
	import StorageAttachmentsSection from '../StorageAttachmentsSection.svelte';
	import { provideInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { auth } from '$lib/stores/auth';
	import { untrack } from 'svelte';

	let { initialInstanceId = 'instance-a' }: { initialInstanceId?: string } = $props();
	let instanceId = $state<string | null>(untrack(() => initialInstanceId));
	let projectId = $state<string | null>('project-a');
	let mismatchedTarget = $state(false);
	let fixedIp = $state('10.0.0.7');
	const controller = {
		get instanceId() { return instanceId ?? undefined; },
		get effectiveProjectId() { return projectId ?? undefined; },
		get instance() { return instanceId ? { id: mismatchedTarget ? 'old-instance' : instanceId, name: 'mutable-name', os_type: 'windows' } : null; },
		get fixedIpsList() { return [{ type: 'fixed', addr: fixedIp, version: 4, network_name: 'private' }]; },
	} as unknown as InstanceDetailController;
	provideInstanceDetailController(controller);
</script>

<button data-testid="clear-instance" onclick={() => instanceId = null}>clear instance</button>
<button data-testid="set-instance-a" onclick={() => instanceId = 'instance-a'}>set instance a</button>
<button data-testid="set-instance-b" onclick={() => instanceId = 'instance-b'}>set instance b</button>
<button data-testid="clear-project" onclick={() => projectId = null}>clear project</button>
<button data-testid="set-project-a" onclick={() => projectId = 'project-a'}>set project a</button>
<button data-testid="set-project-b" onclick={() => projectId = 'project-b'}>set project b</button>
<button data-testid="lose-permission" onclick={() => auth.update(state => ({ ...state, canWrite: false, isSystemAdmin: false, roles: ['reader'] }))}>lose permission</button>
<button data-testid="restore-permission" onclick={() => auth.update(state => ({ ...state, canWrite: true, roles: ['member'] }))}>restore permission</button>
<button data-testid="change-fixed-ip" onclick={() => fixedIp = '10.0.0.9'}>change fixed IP</button>
<button data-testid="mismatch-target" onclick={() => mismatchedTarget = true}>mismatch target</button>
<button data-testid="restore-target" onclick={() => mismatchedTarget = false}>restore target</button>
<StorageAttachmentsSection />
