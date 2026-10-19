<script lang="ts">
  import { t } from '$lib/i18n/ns/palimpsest-local';
  import { getLocale } from '$lib/i18n/runtime.svelte';
  import Card from '$lib/components/ui/Card.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import TextInput from '$lib/components/ui/TextInput.svelte';
  import SelectInput from '$lib/components/ui/SelectInput.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import DocCodeBlock from '$lib/components/docs/DocCodeBlock.svelte';

  let { projectId, packageAuthority = null, namespace = null }: {
    projectId?: string;
    packageAuthority?: string | null;
    namespace?: string | null;
  } = $props();
  let platform = $state('macos');
  let action = $state('inventory');
  let cloudName = $state('openstack');
  let artifactDigest = $state('');
  let publicKeyId = $state('');
  let nativeApiBase = $state('');
  $effect(() => { void [projectId, packageAuthority, namespace]; artifactDigest = ''; publicKeyId = ''; nativeApiBase = ''; });
  const validKeyId = $derived(/^(?:[0-9a-f]{32}|[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})$/.test(publicKeyId.trim()));
  const hub = 'https://palimpsest.dmslab.re.kr';
  const requiresDigest = $derived(action === 'layer' || action === 'image');
  const validDigest = $derived(/^sha256:[0-9a-f]{64}$/.test(artifactDigest.trim()));
  const usableCloud = $derived(cloudName.trim().length > 0 && cloudName.trim().length <= 128);
  const expectedProject = $derived(projectId && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(projectId) ? projectId : null);
  const nativeReady = $derived.by(() => {
    if (!packageAuthority || packageAuthority.length > 255 || !namespace || !/^[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*$/.test(namespace)) return false;
    try {
      const authority = new URL(`https://${packageAuthority}`);
      return !!authority.host && !/[\s/@?#\\]/.test(packageAuthority) && authority.pathname === '/' && !authority.username && !authority.password && !authority.search && !authority.hash;
    } catch { return false; }
  });
  const checkedNativeApi = $derived.by(() => {
    if (!nativeReady) return null;
    try {
      const endpoint = new URL(nativeApiBase.trim());
      return endpoint.protocol === 'https:' && endpoint.host === new URL(`https://${packageAuthority}`).host && !endpoint.username && !endpoint.password && !endpoint.search && !endpoint.hash
        ? endpoint.href.replace(/\/$/, '') : null;
    } catch { return null; }
  });
  function shellQuote(value: string) { return `'${value.replaceAll("'", "'\\''")}'`; }
  const install = 'uv tool install --python 3.11 "palimpsest-client==0.3.5"\npalimpsest --version';
  const offlineWeb = 'palimpsest store ls --kind image\npalimpsest ps\npalimpsest web';
  const controlledWeb = 'palimpsest web --allow-control';
  const nativeProfile = $derived(nativeReady && checkedNativeApi
    ? `palimpsest registry add dmslab ${shellQuote(packageAuthority!)} \\\n  --protocol palimpsest \\\n  --api-base ${shellQuote(checkedNativeApi)} \\\n  --namespace ${namespace}${validKeyId ? ` &&\npalimpsest login --registry dmslab --username ${publicKeyId.trim()}` : ''}`
    : '');
  const sdkCommand = $derived.by(() => {
    const isWeb = action === 'web' || action === 'web-control';
    if (!usableCloud || (requiresDigest && !validDigest)) return '';
    const calls = action === 'layer'
      ? [['palimpsest', 'layer', 'pull', artifactDigest.trim(), '--output', './downloads']]
      : action === 'image'
      ? [['palimpsest', 'image', 'pull', artifactDigest.trim(), '--output', './downloads']]
      : isWeb
      ? [['palimpsest', 'web', ...(action === 'web-control' ? ['--allow-control'] : [])]]
      : [['palimpsest', 'image', 'ls', '--limit', '20'], ['palimpsest', 'layer', 'ls', '--limit', '20']];
    const guard = expectedProject
      ? `    if access.project_id != ${JSON.stringify(expectedProject)}:\n        raise SystemExit("clouds.yaml project does not match the selected project")\n`
      : '    if not access.project_id:\n        raise SystemExit("A project-scoped original account is required")\n';
    const scopeCheck = isWeb ? '' : `    # Legacy CLI commands omit X-Project-Id: fail before using a different default.\n    class NoRedirect(urllib.request.HTTPRedirectHandler):\n        def redirect_request(self, *args, **kwargs):\n            return None\n    request = urllib.request.Request(\n        ${JSON.stringify(hub + '/v1/me')},\n        headers={"X-Auth-Token": environment["PALIMPSEST_TOKEN"]},\n    )\n    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:\n        raw = response.read(65537)\n        if len(raw) > 65536:\n            raise SystemExit("Hub identity response is too large")\n        actor = json.loads(raw)\n    if actor.get("project_id") != access.project_id or actor.get("user_id") != access.user_id:\n        raise SystemExit("CLI default scope differs; use the project-scoped local web action")\n`;
    return `uv run --python 3.11 --with openstacksdk python - <<'PY'
import json
import os
import subprocess
import urllib.request
from openstack.config import OpenStackConfig
from openstack.connection import Connection

cloud = OpenStackConfig(
    config_files=["./clouds.yaml"], secure_files=[], load_envvars=False
).get_one_cloud(cloud=${JSON.stringify(cloudName.trim())})
if not cloud.config.get("auth", {}).get("auth_url", "").startswith("https://"):
    raise SystemExit("HTTPS Keystone authentication is required")
cloud.config["verify"] = True
cloud.config["insecure"] = False
connection = Connection(config=cloud, api_timeout=30)
try:
    connection.authorize()
    access = connection.session.auth.get_access(connection.session)
${guard}    environment = dict(os.environ)
    environment.pop("PALIMPSEST_PACKAGE_KEY", None)
    environment.update(
        PALIMPSEST_URL=${JSON.stringify(hub)},
        PALIMPSEST_TOKEN=connection.session.get_token(),
        PALIMPSEST_PROJECT_ID=access.project_id,
    )
${scopeCheck}${calls.map((args) => `    subprocess.run(${JSON.stringify(args)}, env=environment, check=True)`).join('\n')}
finally:
    connection.close()
PY`;
  });
</script>

<div class="space-y-4">
  <Card surface="base" class="space-y-3">
    <h2 class="text-sm font-semibold">{t('intro.heading')}</h2>
    <p class="text-sm text-ink-2">{t('intro.body')}</p>
    <p class="break-all font-mono text-xs">{hub}</p>
    <Alert tone="info">{t('intro.credentials')}</Alert>
  </Card>

  <Card surface="base" class="space-y-3">
    <h3 class="text-sm font-semibold">{t('install.heading')}</h3>
    <p class="text-sm text-ink-2">{t('install.body')}</p>
    <DocCodeBlock command={{ label: t('install.command'), code: install }} locale={getLocale()} />
    <p class="text-xs text-ink-2">{t('install.path')}</p>
    <div class="grid gap-3 md:grid-cols-2">
      <Field label={t('platform.label')} for="palimpsest-local-platform">
        <SelectInput id="palimpsest-local-platform" bind:value={platform}>
          <option value="macos">{t('platform.macos')}</option>
          <option value="linux">{t('platform.linux')}</option>
          <option value="windows">{t('platform.windows')}</option>
        </SelectInput>
      </Field>
      <p class="self-center text-sm text-ink-2">{t(platform === 'macos' ? 'platform.macosHelp' : platform === 'linux' ? 'platform.linuxHelp' : 'platform.windowsHelp')}</p>
    </div>
  </Card>

  <Card surface="base" class="space-y-3">
    <h3 class="text-sm font-semibold">{t('connect.heading')}</h3>
    <p class="text-sm text-ink-2">{t('connect.body')}</p>
    <p class="text-xs text-ink-2">{t('connect.project')}</p>
    {#if expectedProject}<p class="break-all font-mono text-xs">{expectedProject}</p>{/if}
    <div class="grid gap-3 md:grid-cols-2">
      <Field label={t('connect.cloud')} for="palimpsest-local-cloud" help={t('connect.cloudHelp')}>
        <TextInput id="palimpsest-local-cloud" bind:value={cloudName} maxlength={128} />
      </Field>
      <Field label={t('connect.action')} for="palimpsest-local-action">
        <SelectInput id="palimpsest-local-action" bind:value={action}>
          <option value="inventory">{t('connect.inventory')}</option>
          <option value="layer">{t('connect.layer')}</option>
          <option value="image">{t('connect.image')}</option>
          <option value="web">{t('connect.web')}</option>
          <option value="web-control">{t('connect.webControl')}</option>
        </SelectInput>
      </Field>
    </div>
    {#if action === 'web' || action === 'web-control'}<Alert tone={action === 'web-control' ? 'warning' : 'info'}>{t('connect.webHelp')}</Alert>{/if}
    {#if requiresDigest}
      <Field label={t('connect.digest')} for="palimpsest-local-digest" help={t('connect.digestHelp')}>
        <TextInput id="palimpsest-local-digest" bind:value={artifactDigest} maxlength={71} ariaInvalid={!!artifactDigest && !validDigest} />
      </Field>
      {#if artifactDigest && !validDigest}<Alert tone="warning">{t('connect.invalidDigest')}</Alert>{/if}
    {/if}
    {#if sdkCommand}<DocCodeBlock command={{ label: t('connect.command'), code: sdkCommand }} locale={getLocale()} />
    {:else}<p role="status" class="text-sm text-ink-2">{t('connect.inputRequired')}</p>{/if}
    <p class="text-xs text-ink-2">{t('connect.tokenLifetime')}</p>
  </Card>

  <Card surface="base" class="space-y-3">
    <h3 class="text-sm font-semibold">{t('local.heading')}</h3>
    <p class="text-sm text-ink-2">{t('local.body')}</p>
    <DocCodeBlock command={{ label: t('local.command'), code: offlineWeb }} locale={getLocale()} />
    <Alert tone="info">{t('local.foreground')}</Alert>
    <p class="text-sm text-ink-2">{t('local.control')}</p>
    <DocCodeBlock command={{ label: t('local.controlCommand'), code: controlledWeb }} locale={getLocale()} />
    <p class="text-xs text-ink-2">{t('local.layerBoundary')}</p>
  </Card>

  <Card surface="base" class="space-y-3">
    <h3 class="text-sm font-semibold">{t('native.heading')}</h3>
    <p class="text-sm text-ink-2">{t('native.body')}</p>
    <Alert tone="warning">{t('native.policy')}</Alert>
    {#if nativeReady}
      <Field label={t('native.apiBase')} for="palimpsest-local-native-api" help={t('native.apiBaseHelp')}>
        <TextInput id="palimpsest-local-native-api" type="url" bind:value={nativeApiBase} maxlength={2048} ariaInvalid={!!nativeApiBase && !checkedNativeApi} />
      </Field>
      <Field label={t('native.keyId')} for="palimpsest-local-key-id" help={t('native.keyIdHelp')}>
        <TextInput id="palimpsest-local-key-id" bind:value={publicKeyId} maxlength={36} ariaInvalid={!!publicKeyId && !validKeyId} />
      </Field>
      {#if nativeProfile}<DocCodeBlock command={{ label: t('native.command'), code: nativeProfile }} locale={getLocale()} />
      {:else}<p role="status" class="text-xs text-ink-2">{t('native.apiRequired')}</p>{/if}
      <p class="text-xs text-ink-2">{t('native.helper')}</p>
    {:else}<p class="text-sm text-ink-2">{t('native.notReady')}</p>{/if}
    <div class="flex flex-wrap gap-2">
      <Button variant="secondary" href="https://github.com/openstack-afterglow/palimpsest/blob/dev/docs/registries.md" target="_blank" rel="noopener noreferrer">{t('native.docs')}</Button>
      <Button variant="ghost" href="https://github.com/openstack-afterglow/palimpsest/blob/dev/docs/install.md" target="_blank" rel="noopener noreferrer">{t('install.docs')}</Button>
    </div>
  </Card>
</div>
