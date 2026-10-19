<script lang="ts">
  import type { PackageIdentity } from '$lib/api/palimpsestPackages';

  let { identity, projectId, packageAuthority, namespace }: {
    identity?: PackageIdentity | null;
    projectId?: string;
    packageAuthority?: string | null;
    namespace?: string | null;
  } = $props();
</script>

<div
  data-testid={identity !== undefined ? 'hub-panel' : 'local-guide'}
  data-project-id={identity?.projectId ?? projectId ?? ''}
  data-user-id={identity?.userId ?? ''}
  data-authority={packageAuthority ?? ''}
  data-namespace={namespace ?? ''}
></div>
