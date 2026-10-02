<script lang="ts">
  import { onMount } from 'svelte';
  import { beforeNavigate } from '$app/navigation';
  import { page } from '$app/stores';
  import { derived, get } from 'svelte/store';
  import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
  import { createPalimpsestPackagesController } from '$lib/stores/palimpsestPackagesController.svelte';
  import type { KeyAction, PackageIdentity, PackageSummary, Platform, PackageKey } from '$lib/api/palimpsestPackages';
  import { samePackageIdentity } from '$lib/api/palimpsestPackages';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import Card from '$lib/components/ui/Card.svelte';
  import TableShell from '$lib/components/ui/TableShell.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Modal from '$lib/components/ui/Modal.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import TextInput from '$lib/components/ui/TextInput.svelte';
  import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';

  const selectedIdentity = derived([auth, authReady, projectSwitching, logoutInProgress], ([$auth, ready, switching, loggingOut]): PackageIdentity | null =>
    ready && !switching && !loggingOut && $auth.token && $auth.projectId && $auth.userId
      ? { token: $auth.token, projectId: $auth.projectId, userId: $auth.userId } : null);
  const controller = createPalimpsestPackagesController(() => get(selectedIdentity));
  let tab = $state('inventory');
  let showCreate = $state(false);
  let keyName = $state('');
  let packageNames = $state('');
  let allPackages = $state(false);
  let actions = $state<KeyAction[]>(['packages:read']);
  let expiryDays = $state('30');
  let formError = $state('');
  let copyMessage = $state('');
  let revokeTarget = $state<PackageKey | null>(null);
  let linkHandled = '';
  const actionChoices: { value: KeyAction; label: string }[] = [
    { value: 'packages:read', label: '패키지 읽기' }, { value: 'packages:write', label: '패키지 쓰기' },
    { value: 'cache:read', label: '캐시 읽기' }, { value: 'cache:write', label: '캐시 쓰기' },
  ];
  function resetForm() {
    showCreate = false; keyName = ''; packageNames = ''; allPackages = false;
    actions = ['packages:read']; expiryDays = '30'; formError = ''; copyMessage = ''; revokeTarget = null;
  }
  onMount(() => {
    let previous: PackageIdentity | null = null;
    const stop = selectedIdentity.subscribe((identity) => {
      if (!samePackageIdentity(previous, identity)) { resetForm(); linkHandled = ''; tab = 'inventory'; }
      previous = identity;
      controller.bindIdentity();
    });
    const leave = () => { resetForm(); controller.discardSecret(); };
    window.addEventListener('pagehide', leave);
    return () => { stop(); window.removeEventListener('pagehide', leave); controller.dispose(); };
  });
  beforeNavigate(() => { resetForm(); controller.discardSecret(); });
  $effect(() => {
    const context = controller.context;
    const name = $page.url.searchParams.get('package');
    const namespace = $page.url.searchParams.get('namespace') ?? undefined;
    const digest = $page.url.searchParams.get('digest') ?? undefined;
    const key = `${context?.project_id}:${name}:${namespace}:${digest}`;
    if (context?.namespace && context.capabilities.packages_read && name && key !== linkHandled) {
      linkHandled = key;
      void controller.openPackage(name, digest, namespace);
    }
  });
  function changeTab(value: string) {
    controller.discardSecret(); resetForm(); controller.closeDetail(); tab = value;
    if (value === 'keys') void controller.loadKeys();
  }
  function platforms(values: Platform[]) { return values.map((item) => `${item.os}/${item.architecture}${item.variant ? `/${item.variant}` : ''}`).join(', ') || '플랫폼 메타데이터 없음'; }
  function timestamp(value: string | null) { return value ? new Date(value).toLocaleString() : '기록 없음'; }
  function size(value: number) { return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value / 1024 / 1024) + ' MiB'; }
  function packageType(value: string) { return value === 'runtime-bundle' ? '런타임 번들' : 'OCI 이미지'; }
  async function copyReference(name: string, digest: string) {
    const context = controller.context;
    if (!context?.namespace || !context.package_authority) { copyMessage = '신뢰된 패키지 공개 주소가 설정되지 않아 참조를 복사할 수 없습니다.'; return; }
    await copy(`${context.package_authority}/${context.namespace}/${name}@${digest}`);
  }
  async function copy(value: string, secret = false) {
    const actor = get(selectedIdentity);
    const issued = controller.issued;
    copyMessage = '';
    try {
      await navigator.clipboard.writeText(value);
      if (samePackageIdentity(actor, get(selectedIdentity)) && (!secret || issued === controller.issued)) copyMessage = '클립보드에 복사했습니다.';
    } catch {
      if (samePackageIdentity(actor, get(selectedIdentity)) && (!secret || issued === controller.issued)) copyMessage = '클립보드에 접근할 수 없습니다. 표시된 값을 직접 복사해 주세요.';
    }
  }
  function toggleAction(action: KeyAction, checked: boolean) {
    actions = checked ? [...actions, action] : actions.filter((value) => value !== action);
  }
  async function createKey(event: SubmitEvent) {
    event.preventDefault(); formError = '';
    const names = packageNames.split(/[\s,]+/).filter(Boolean);
    const days = Number(expiryDays);
    if (!keyName.trim()) { formError = '키 이름을 입력해 주세요.'; return; }
    if (!Number.isInteger(days) || days < 1 || days > 90) { formError = '만료 기간은 1–90일의 정수여야 합니다.'; return; }
    if (!allPackages && (names.length < 1 || names.length > 32 || new Set(names).size !== names.length || names.some((name) => name.split('/').some((component) => !/^[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*$/.test(component)) || `${controller.context?.namespace}/${name}`.length > 255))) {
      formError = '정확한 소문자 패키지 이름을 1–32개 입력해 주세요. 중복·와일드카드·태그는 사용할 수 없습니다.'; return;
    }
    if (!actions.length || (actions.includes('packages:write') && !actions.includes('packages:read')) || (actions.includes('cache:write') && !actions.includes('cache:read'))) {
      formError = '최소 한 권한을 선택하세요. 각 쓰기 권한은 해당 읽기 권한이 필요합니다.'; return;
    }
    await controller.issueKey({ name: keyName.trim(), scope: allPackages ? { all_packages: true } : { packages: names }, actions, expires_in_days: days });
    if (controller.issued) showCreate = false;
  }
  function keyStatus(key: PackageKey) { return key.revoked_at ? '폐기됨' : new Date(key.expires_at).getTime() <= Date.now() ? '만료됨' : '사용 가능'; }
  // Table cells show a recognizable digest prefix; the title, details and copied references keep the exact value.
  function shortDigest(digest: string) { return digest.length > 19 ? `${digest.slice(0, 19)}…` : digest; }
</script>

<svelte:head><title>Palimpsest 패키지 · Afterglow</title></svelte:head>
<PageShell>
  <PageHeader breadcrumb="Palimpsest" title="프로젝트 패키지" subtitle="선택한 프로젝트의 비공개 Hub 패키지와 내 접근 키를 관리합니다. 서버 빌드 스튜디오와 별도입니다.">
    {#snippet actions()}<Button variant="secondary" disabled={!$selectedIdentity || !!controller.busy.context || !!controller.busy.issue || !!controller.busy.revoke || !!controller.busy.register} onclick={() => { controller.discardSecret(); controller.closeDetail(); void controller.loadContext(); if (tab === 'keys') void controller.loadKeys(); }}>새로고침</Button>{/snippet}
  </PageHeader>
  <div class="space-y-4">
    {#if !controller.context}
      {#if controller.errors.context}<Alert tone="danger">{controller.errors.context}</Alert><Button variant="secondary" onclick={() => controller.loadContext()}>다시 조회</Button>
      {:else}<p class="text-sm text-ink-2" role="status">현재 프로젝트와 인증 컨텍스트를 확인하는 중…</p>{/if}
    {:else}
      <Card surface="base">
        <p class="break-words text-sm font-medium">{controller.context.project_name}</p>
        <p class="mt-1 break-all font-mono text-xs text-ink-2">{controller.context.project_id}</p>
        <p class="mt-2 text-sm">네임스페이스: <span class="font-mono">{controller.context.namespace ?? '미등록'}</span> · 프로젝트 비공개</p>
        {#if controller.context.namespace && !controller.context.package_authority}<p class="mt-2 text-xs text-ink-2">신뢰된 패키지 공개 주소가 설정되지 않아 참조 복사는 사용할 수 없습니다. 상세 조회와 인증된 다운로드는 가능합니다.</p>{/if}
      </Card>
      {#if !controller.context.namespace}
        <Card surface="base">
          <h2 class="text-sm font-semibold">프로젝트 네임스페이스가 등록되지 않았습니다</h2>
          <p class="my-3 text-sm text-ink-2">등록하면 이 프로젝트에 고정된 네임스페이스가 생성됩니다. 패키지 조회와 키 발급은 등록 후 사용할 수 있습니다.</p>
          {#if controller.context.capabilities.packages_write}<Button disabled={!!controller.busy.register} onclick={() => controller.register()}>{controller.busy.register ? '등록 중…' : '프로젝트 네임스페이스 등록'}</Button>
          {:else}<p class="text-sm text-ink-2">등록 가능한 일반 프로젝트 멤버에게 등록을 요청하세요. 현재 계정에는 등록 권한이 없습니다.</p>{/if}
          {#if controller.errors.register}<Alert tone="danger" class="mt-3">{controller.errors.register}</Alert>{/if}
        </Card>
      {:else}
        <Tabs id="package-tabs" value={tab} ariaLabel="패키지 관리" items={[{ value: 'inventory', label: '패키지', panelId: 'package-inventory' }, { value: 'keys', label: '내 접근 키', panelId: 'package-keys' }]} onchange={changeTab} />
        {#if tab === 'inventory'}
          <div id="package-inventory" role="tabpanel" aria-labelledby="package-tabs-inventory" tabindex="0" class="space-y-4">
            {#if controller.errors.inventory}<Alert tone="danger">{controller.errors.inventory}</Alert><Button variant="secondary" onclick={() => controller.loadInventory()}>목록 다시 조회</Button>{/if}
            {#if !controller.context.capabilities.packages_read}<Alert tone="warning">현재 계정에 패키지 읽기 권한이 없습니다.</Alert>
            {:else if controller.busy.inventory && controller.inventory === null}<p class="text-sm text-ink-2" role="status">패키지를 불러오는 중…</p>
            {:else if controller.inventory !== null}
              {#if controller.inventory.length === 0}<Card surface="base"><p class="text-sm text-ink-2">아직 게시된 패키지가 없습니다. 이 프로젝트 키로 CLI에서 게시한 패키지는 승인 없이 이곳에 나타납니다.</p></Card>
              {:else}
                <div class="hidden xl:block"><TableShell><table><thead><tr><th scope="col">패키지 / 유형</th><th scope="col">태그 / digest</th><th scope="col">플랫폼</th><th scope="col">검증된 크기 / 최근 게시</th><th scope="col">작업</th></tr></thead><tbody>
                  {#each controller.inventory as item (item.package_id)}<tr>
                    <td><span class="font-mono">{item.namespace}/{item.name}</span><p class="mt-1 text-xs text-ink-2">{packageType(item.package_type)} · {item.version_count} 버전</p></td>
                    <td>{#each item.tags as tag}<p class="font-mono text-xs" title={tag.digest}>{tag.tag} → {shortDigest(tag.digest)}</p>{/each}{#if !item.tags.length}<span class="text-ink-2">태그 없음 · 이력에서 digest 확인</span>{/if}</td>
                    <td class="max-w-56 whitespace-normal">{platforms(item.platforms)}</td><td>{@render latestMetadata(item, true)}<p class="max-w-56 break-all text-xs">{item.latest_pushed_by ?? '게시자 기록 없음'}</p><p class="text-xs text-ink-2 tabular-nums">{timestamp(item.latest_pushed_at)}</p></td>
                    <td>{@render packageActions(item, true)}</td>
                  </tr>{/each}
                </tbody></table></TableShell></div>
                <div class="space-y-3 xl:hidden">{#each controller.inventory as item (item.package_id)}<Card surface="base">
                  <h2 class="break-all font-mono text-sm font-medium">{item.namespace}/{item.name}</h2><p class="mt-1 text-xs text-ink-2">{packageType(item.package_type)} · {item.version_count} 버전 · 프로젝트 비공개</p>
                  <div class="my-3 space-y-1 text-xs">{#each item.tags as tag}<p class="break-all font-mono">{tag.tag} → {tag.digest}</p>{/each}{#if !item.tags.length}<p>태그 없음 · 이력에서 digest 확인</p>{/if}<p>{platforms(item.platforms)}</p><p class="break-all">{item.latest_pushed_by ?? '게시자 기록 없음'} · {timestamp(item.latest_pushed_at)}</p></div>
                  {@render latestMetadata(item)}
                  {@render packageActions(item)}
                </Card>{/each}</div>
              {/if}
              {#if controller.nextCursor}<Button variant="secondary" disabled={!!controller.busy.inventory} onclick={() => controller.loadInventory(true)}>패키지 더 보기</Button>{/if}
            {/if}
            {#if controller.errors.detail}<Alert tone="danger">{controller.errors.detail}</Alert>{/if}
            {#if controller.busy.detail && !controller.detail}<p class="text-sm text-ink-2" role="status">패키지 이력을 불러오는 중…</p>{/if}
            {#if controller.errors.download}<Alert tone="danger">{controller.errors.download}</Alert>{/if}
          </div>
        {:else}
          <div id="package-keys" role="tabpanel" aria-labelledby="package-tabs-keys" tabindex="0" class="space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-3"><p class="text-sm text-ink-2">현재 프로젝트에서 내가 발급한 키만 표시합니다. 캐시 권한은 패키지 권한과 별도입니다.</p><Button disabled={!controller.context.capabilities.keys_issue || !!controller.busy.issue || !!controller.busy.revoke || !!controller.issued} onclick={() => { resetForm(); showCreate = true; }}>키 발급</Button></div>
            {#if !controller.context.capabilities.keys_issue}<Alert tone="warning">현재 계정에는 키 발급 권한이 없습니다.</Alert>{/if}
            {#if controller.errors.keys}<Alert tone="danger">{controller.errors.keys}</Alert><Button variant="secondary" onclick={() => controller.loadKeys()}>키 다시 조회</Button>{/if}
            {#if controller.errors.issue}<Alert tone="danger">{controller.errors.issue}</Alert>{/if}
            {#if controller.errors.revoke}<Alert tone="danger">{controller.errors.revoke}</Alert>{/if}
            {#if controller.busy.keys}<p class="text-sm text-ink-2" role="status">내 키를 불러오는 중…</p>{:else if controller.keys !== null}
              {#if !controller.keys.length}<Card surface="base"><p class="text-sm text-ink-2">발급한 키가 없습니다.</p></Card>{:else}
                <div class="hidden md:block"><TableShell><table><thead><tr><th scope="col">키 / 상태</th><th scope="col">정확한 범위</th><th scope="col">권한</th><th scope="col">발급 / 만료</th><th scope="col">작업</th></tr></thead><tbody>{#each controller.keys as key (key.key_id)}<tr><td>{key.name}<div class="mt-1"><StatusChip status={keyStatus(key)} /></div></td><td class="max-w-64 break-all">{key.scope.all_packages ? '이 프로젝트의 모든 패키지' : key.scope.packages.join(', ')}</td><td class="max-w-56 break-words font-mono text-xs">{key.actions.join(', ')}</td><td class="tabular-nums">{timestamp(key.created_at)}<p class="text-xs text-ink-2">{timestamp(key.expires_at)}</p></td><td>{@render keyRevoke(key)}</td></tr>{/each}</tbody></table></TableShell></div>
                <div class="space-y-3 md:hidden">{#each controller.keys as key (key.key_id)}<Card surface="base"><div class="flex flex-wrap items-center justify-between gap-2"><h2 class="text-sm font-medium">{key.name}</h2><StatusChip status={keyStatus(key)} /></div><p class="my-2 break-all text-sm">{key.scope.all_packages ? '이 프로젝트의 모든 패키지' : key.scope.packages.join(', ')}</p><p class="break-words font-mono text-xs">{key.actions.join(', ')}</p><p class="my-3 text-xs text-ink-2">발급 {timestamp(key.created_at)} · 만료 {timestamp(key.expires_at)}</p>{@render keyRevoke(key)}</Card>{/each}</div>
              {/if}
            {/if}
          </div>
        {/if}
      {/if}
    {/if}
    {#if copyMessage}<p role="status" class="text-sm text-ink-2">{copyMessage}</p>{/if}
  </div>
</PageShell>

{#snippet packageActions(item: PackageSummary, stacked = false)}
  {@const digest = controller.latestVersions[item.package_id]?.version?.root_digest ?? item.tags[0]?.digest}
  <!-- Table rows stack actions so the max-content table keeps every action visible. -->
  <div class={stacked ? 'flex flex-col items-start gap-2' : 'flex flex-wrap gap-2'}><Button variant="secondary" onclick={() => controller.openPackage(item.name)}>상세 / 이력</Button>{#if digest}<Button variant="ghost" disabled={!controller.context?.package_authority} onclick={() => copyReference(item.name, digest)}>참조 복사</Button><Button variant="ghost" disabled={!!controller.busy.download} onclick={() => controller.download(item.name, digest)}>다운로드</Button>{/if}</div>
{/snippet}
{#snippet latestMetadata(item: PackageSummary, compact = false)}
  {@const latest = controller.latestVersions[item.package_id]}
  {#if latest?.version}
    <p class="text-xs tabular-nums">{size(latest.version.total_bytes)} · 최신 버전의 검증된 graph 크기</p>
    <p class="max-w-72 break-all font-mono text-xs text-ink-2" title={latest.version.root_digest}>최근 digest: {compact ? shortDigest(latest.version.root_digest) : latest.version.root_digest}</p>
  {:else if !latest}<p class="text-xs text-ink-2" role="status">최신 버전 크기 확인 중…</p>
  {:else}<p class="max-w-72 text-xs text-state-warning-text">최신 버전 크기 확인 불가 · {latest.error}</p>{/if}
{/snippet}
{#snippet keyRevoke(key: PackageKey)}<Button variant="danger-outline" disabled={!!key.revoked_at || !!controller.busy.issue || !!controller.busy.revoke} onclick={() => { revokeTarget = key; }}>폐기</Button>{/snippet}

<Modal open={!!controller.detail} ariaLabel="패키지 상세와 버전 이력" onClose={() => controller.closeDetail()}>
  {#if controller.detail}<Card surface="modal" class="w-full max-w-full md:w-[48rem] space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3"><h2 class="break-all font-mono text-sm font-semibold">{controller.detail.namespace}/{controller.detail.name}</h2><Button variant="ghost" onclick={() => controller.closeDetail()}>닫기</Button></div>
    {#if copyMessage}<p role="status" class="text-sm text-ink-2">{copyMessage}</p>{/if}
    <p class="text-sm text-ink-2">{packageType(controller.detail.package_type)} · 프로젝트 비공개 · {platforms(controller.detail.platforms)}</p>
    <div class="flex flex-wrap gap-2">{#each controller.detail.tags as tag}<Button variant="secondary" disabled={!!controller.busy.version} onclick={() => controller.resolveTag(tag.tag)}>{tag.tag} 해석</Button>{/each}</div>
    <h3 class="text-sm font-semibold">버전 이력 · 검증된 크기</h3>
    {#if controller.errors.detail}<Alert tone="danger">{controller.errors.detail}</Alert>{/if}
    {#each controller.versions ?? [] as item (item.root_digest)}
      <Card surface="base" padding="sm">
        <p class="break-all font-mono text-xs">{item.root_digest}</p>
        <p class="my-2 text-xs text-ink-2">{size(item.total_bytes)} · {platforms(item.platforms)} · {item.pushed_by} · {timestamp(item.pushed_at)}</p>
        <div class="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={!!controller.busy.version} onclick={() => controller.selectVersion(item.root_digest)}>버전 상세</Button>
          <Button variant="ghost" disabled={!controller.context?.package_authority} onclick={() => copyReference(item.package, item.root_digest)}>참조 복사</Button>
          <Button variant="ghost" disabled={!!controller.busy.download} onclick={() => controller.download(item.package, item.root_digest)}>다운로드</Button>
        </div>
      </Card>
    {/each}
    {#if controller.versionsCursor}<Button variant="secondary" disabled={!!controller.busy.detail} onclick={() => controller.moreVersions()}>버전 더 보기</Button>{/if}
    {#if controller.busy.version}<p role="status" class="text-sm text-ink-2">버전 상세를 확인하는 중…</p>{/if}
    {#if controller.errors.version}<Alert tone="danger">{controller.errors.version}</Alert>{/if}
    {#if controller.errors.download}<Alert tone="danger">{controller.errors.download}</Alert>{/if}
    {#if controller.version}<Card surface="base" class="space-y-2 text-sm"><h3 class="font-semibold">선택한 버전</h3><p class="break-all font-mono text-xs">{controller.version.root_digest}</p><p>미디어 유형: {controller.version.root_media_type}</p><p>검증된 크기 {size(controller.version.total_bytes)} · 다운로드 {size(controller.version.archive_size_bytes)}</p><p>{controller.version.pushed_by} · {timestamp(controller.version.pushed_at)}</p><h4 class="font-medium">클라이언트 출처 정보</h4><pre class="max-h-64 overflow-auto whitespace-pre-wrap break-all font-mono text-xs">{JSON.stringify(controller.version.provenance, null, 2)}</pre><h4 class="font-medium">검증된 descriptor graph</h4><pre class="max-h-64 overflow-auto whitespace-pre-wrap break-all font-mono text-xs">{JSON.stringify(controller.version.graph, null, 2)}</pre></Card>{/if}
  </Card>{/if}
</Modal>

<Modal open={showCreate} dismissible={!controller.busy.issue} ariaLabel="프로젝트 접근 키 발급" onClose={() => { showCreate = false; controller.discardSecret(); }}>
  <Card surface="modal" class="w-full max-w-full md:w-[32rem]">
    <form onsubmit={createKey} class="space-y-4">
      <h2 class="text-sm font-semibold">접근 키 발급</h2>
      <Field label="키 이름" for="package-key-name" required><TextInput id="package-key-name" bind:value={keyName} disabled={!!controller.busy.issue} required maxlength={128} /></Field>
      <fieldset class="space-y-2 text-sm"><legend class="mb-2 text-xs font-medium text-ink-1">패키지 범위</legend>
        <ToggleGroup value={allPackages ? 'all' : 'exact'} ariaLabel="패키지 키 범위" fullWidth options={[{value: 'exact', label: '정확한 패키지 이름', disabled: !!controller.busy.issue}, {value: 'all', label: '모든 프로젝트 패키지', disabled: !!controller.busy.issue}]} onchange={(value) => allPackages = value === 'all'} />
        {#if allPackages}<p class="text-xs text-ink-2">이 프로젝트의 현재 및 앞으로 생성되는 모든 패키지에 명시적으로 권한을 부여합니다.</p>{/if}
      </fieldset>
      {#if !allPackages}<Field label="패키지 이름" for="package-key-packages" help="쉼표 또는 공백으로 구분합니다. 아직 게시하지 않은 이름도 지정할 수 있습니다. 하위 패키지는 별도 이름입니다."><TextInput id="package-key-packages" bind:value={packageNames} disabled={!!controller.busy.issue} placeholder="test, team/image" required /></Field>{/if}
      <fieldset class="space-y-2 text-sm"><legend class="mb-2 text-xs font-medium text-ink-1">허용 작업 · 캐시는 별도 권한</legend>
        {#each actionChoices as action}<div class="flex flex-wrap items-center gap-2"><SelectionCheckbox checked={actions.includes(action.value)} disabled={!!controller.busy.issue || (!controller.context?.capabilities.packages_write && (action.value === 'packages:write' || action.value === 'cache:write'))} ariaLabel={action.label} onclick={() => toggleAction(action.value, !actions.includes(action.value))} />{action.label}<span class="font-mono text-xs text-ink-2">{action.value}</span></div>{/each}
      </fieldset>
      {#if !controller.context?.capabilities.packages_write}<p class="text-xs text-ink-2">현재 프로젝트 권한으로는 읽기 전용 키만 발급할 수 있습니다.</p>{/if}
      <Field label="만료 기간 (일)" for="package-key-expiry" help="1–90일. 키는 자동 갱신되지 않습니다."><TextInput id="package-key-expiry" type="number" inputmode="numeric" bind:value={expiryDays} disabled={!!controller.busy.issue} required /></Field>
      {#if formError}<Alert tone="danger">{formError}</Alert>{/if}{#if controller.errors.issue}<Alert tone="danger">{controller.errors.issue}</Alert>{/if}
      <div class="flex flex-wrap justify-end gap-2"><Button variant="secondary" disabled={!!controller.busy.issue} onclick={() => { showCreate = false; controller.discardSecret(); }}>취소</Button><Button type="submit" disabled={!!controller.busy.issue}>{controller.busy.issue ? '발급 중…' : '키 발급'}</Button></div>
    </form>
  </Card>
</Modal>
<Modal open={!!controller.issued} dismissible={false} ariaLabel="한 번만 표시되는 접근 키" onClose={() => { controller.discardSecret(); copyMessage = ''; }}>
  {#if controller.issued}<Card surface="modal" class="w-full md:w-[32rem] space-y-4"><h2 class="text-sm font-semibold">키가 발급되었습니다 · 한 번만 표시</h2><Alert tone="warning">이 키는 다시 조회할 수 없습니다. 안전한 자격 증명 저장소로 복사하세요. 화면을 닫거나 프로젝트를 전환하면 이 값은 폐기됩니다.</Alert><p class="text-sm">{controller.issued.key.name} · 만료 {timestamp(controller.issued.key.expires_at)}</p><pre class="select-all whitespace-pre-wrap break-all rounded-md bg-surface-sunken p-3 font-mono text-xs">{controller.issued.secret}</pre>{#if copyMessage}<p role="status" class="text-sm text-ink-2">{copyMessage}</p>{/if}<div class="flex flex-wrap justify-end gap-2"><Button variant="secondary" onclick={() => copy(controller.issued!.secret, true)}>키 복사</Button><Button onclick={() => { controller.discardSecret(); copyMessage = ''; }}>복사 완료 · 화면에서 폐기</Button></div></Card>{/if}
</Modal>
<Modal open={!!revokeTarget} ariaLabel="접근 키 폐기 확인" onClose={() => revokeTarget = null}>
  {#if revokeTarget}<Card surface="modal" class="w-full md:w-[28rem] space-y-4"><h2 class="text-sm font-semibold">키 폐기</h2><p class="text-sm">{revokeTarget.name} 키를 폐기할까요? 이 키로 새 요청이나 진행 중인 게시를 완료할 수 없게 됩니다.</p><div class="flex flex-wrap justify-end gap-2"><Button variant="secondary" onclick={() => revokeTarget = null}>취소</Button><Button variant="danger" onclick={() => { const key = revokeTarget!; revokeTarget = null; void controller.revokeKey(key); }}>폐기</Button></div></Card>{/if}
</Modal>
