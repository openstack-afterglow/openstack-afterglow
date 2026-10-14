<script lang="ts">
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { auth, authReady, projectSwitching } from '$lib/stores/auth';
  import { createLoginMonitoringController } from '$lib/stores/loginMonitoringController.svelte';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import Card from '$lib/components/ui/Card.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import TextInput from '$lib/components/ui/TextInput.svelte';
  import SelectInput from '$lib/components/ui/SelectInput.svelte';
  import TableShell from '$lib/components/ui/TableShell.svelte';
  import LoginCharts from './LoginCharts.svelte';
  import { t } from '$lib/i18n/ns/login-monitoring';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import type { LoginWindow } from '$lib/types/loginMonitoring';
  const ctrl = createLoginMonitoringController();
  let search = $state('');
  const filtered = $derived(ctrl.users.filter(user => user.id === ctrl.selectedUser || `${user.name} ${user.id}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())));
  const date = (value: string | null) => value ? new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(value)) : t('unknown');
  const number = (value: number | null) => value === null ? t('unknown') : new Intl.NumberFormat(intlLocale()).format(value);
  function errorMessage(code: string) {
    if (code === 'login_monitoring_native_denied') return t('nativeDenied');
    if (code === 'login_monitoring_admin_denied') return t('adminDenied');
    if (code === 'login_monitoring_directory_unavailable') return t('directoryUnavailable');
    if (code === 'login_monitoring_user_not_found') return t('notFound');
    return t('unavailable');
  }
  onMount(() => {
    const sync = () => {
      const state = get(auth);
      ctrl.setAuthority({ token: state.token ?? undefined, userId: state.userId ?? undefined, projectId: state.projectId ?? undefined, admin: state.isSystemAdmin, ready: get(authReady) && !get(projectSwitching) });
    };
    const subscriptions = [auth.subscribe(sync), authReady.subscribe(sync), projectSwitching.subscribe(sync)];
    return () => { subscriptions.forEach(unsubscribe => unsubscribe()); ctrl.dispose(); };
  });
</script>

<PageShell>
  <PageHeader title={t('title')} breadcrumb={t('breadcrumb')}>
    {#snippet actions()}<Button variant="secondary" disabled={!ctrl.allowed || ctrl.loading || !ctrl.selectedUser} onclick={ctrl.load}>{t('refresh')}</Button>{/snippet}
  </PageHeader>
  <Alert tone="info" class="mb-4">{t('notice')}</Alert>
  {#if $authReady && !$projectSwitching && !$auth.isSystemAdmin}<Alert class="mb-4">{t('adminDenied')}</Alert>{/if}
  <Card surface="base" class="mb-4">
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <Field label={t('search')} help={t('searchNotice')}><TextInput type="search" bind:value={search} ariaLabel={t('search')} disabled={!ctrl.allowed} /></Field>
      <Field label={t('user')}><SelectInput value={ctrl.selectedUser} ariaLabel={t('user')} disabled={!ctrl.allowed} onchange={event => ctrl.selectUser((event.currentTarget as HTMLSelectElement).value)}>
        <option value="">{t('select')}</option>{#each filtered as user (user.id)}<option value={user.id}>{user.name} · {user.id}</option>{/each}
      </SelectInput></Field>
      <Field label={t('range')}><SelectInput value={ctrl.window} ariaLabel={t('range')} onchange={event => ctrl.selectWindow((event.currentTarget as HTMLSelectElement).value as LoginWindow)}>
        <option value="24h">{t('range24h')}</option><option value="7d">{t('range7d')}</option><option value="30d">{t('range30d')}</option>
      </SelectInput></Field>
    </div>
    <div class="mt-3 flex flex-wrap items-center gap-3">
      <Button variant="ghost" disabled={!ctrl.allowed || ctrl.directoryLoading} onclick={() => ctrl.loadUsers()}>{t('refresh')}</Button>
      {#if ctrl.nextMarker}<Button variant="secondary" disabled={ctrl.directoryLoading} onclick={() => ctrl.loadUsers(true)}>{t('more')}</Button>{/if}
      {#if ctrl.directoryLoading}<p role="status" class="text-sm text-ink-2">{t('directoryLoading')}</p>{/if}
      {#if search && !filtered.length && !ctrl.directoryLoading}<p class="text-sm text-ink-2">{t('noMatches')}</p>{/if}
    </div>
    {#if ctrl.directoryError}<Alert class="mt-3">{errorMessage(ctrl.directoryError)}<Button variant="ghost" onclick={() => ctrl.loadUsers(!!ctrl.nextMarker)}>{t('retry')}</Button></Alert>{/if}
  </Card>
  {#if ctrl.loading}<p role="status" class="text-sm text-ink-2">{t('loading')}</p>{/if}
  {#if ctrl.error}<Alert>{errorMessage(ctrl.error)}<Button variant="ghost" onclick={ctrl.load}>{t('retry')}</Button></Alert>{/if}
  {#if ctrl.allowed && ctrl.data}
    {@const data = ctrl.data}
    <p class="text-sm font-medium break-all">{data.user.name} · {data.user.id}</p>
    <p class="text-xs text-ink-2 mb-4">{t('snapshot', { at: date(data.as_of) })}</p>
    <Alert tone="warning" class="mb-4">{t('failuresNotice')}</Alert>
    {#if data.history.state === 'unavailable'}<Alert class="mb-4">{t('historyUnavailable')}</Alert>{/if}
    {#if data.history.state === 'partial'}<Alert tone="warning" class="mb-4">{t('historyPartial')}</Alert>{/if}
    <dl class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
      {#each [{ label: t('successes'), value: data.history.login_successes }, { label: t('failures'), value: data.history.failure_history === 'not_collected' && data.history.recorded_login_failures === 0 ? null : data.history.recorded_login_failures }, { label: t('validSessions'), value: data.sessions.valid_count }, { label: t('observed'), value: data.sessions.observed_recent_count }] as stat}
        <Card surface="base"><dt class="text-xs text-ink-2">{stat.label}</dt><dd class="text-xl font-semibold tabular-nums mt-2">{number(stat.value)}</dd></Card>
      {/each}
    </dl>
    {#if data.history.timeline && data.history.hour_distribution}<LoginCharts timeline={data.history.timeline} hours={data.history.hour_distribution} />{/if}
    <section class="mt-6 space-y-3" aria-label={t('validSessions')}>
      <h2 class="text-sm font-semibold">{t('validSessions')}</h2>
      <p class="text-sm text-ink-2">{t('sessionsNotice')}</p>
      <Alert tone="info">{t('observationNotice')}</Alert>
      {#if data.sessions.state === 'unavailable'}<Alert>{t('sessionsUnavailable')}</Alert>
      {:else if data.sessions.state === 'unknown'}<Alert tone="warning">{t('sessionsUnknown')}</Alert>
      {:else if data.sessions.state === 'partial'}<Alert tone="warning">{t('sessionsPartial')}</Alert>{/if}
      {#if data.sessions.state === 'ready' && data.sessions.items?.length === 0}<p class="text-sm text-ink-2">{t('emptySessions')}</p>{/if}
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {#each data.sessions.items ?? [] as session}
          <Card surface="base"><dl class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm break-words">
            <div><dt class="text-xs text-ink-2">{t('started')}</dt><dd class="tabular-nums">{date(session.started_at)}</dd></div>
            <div><dt class="text-xs text-ink-2">{t('lastSeen')}</dt><dd class="tabular-nums">{date(session.last_seen)}</dd><dd class="text-xs text-ink-2">{session.observed_recently ? t('recently') : t('notRecently')}</dd></div>
            <div><dt class="text-xs text-ink-2">{t('expiry')}</dt><dd class="tabular-nums">{date(session.expires_at)}</dd></div>
            <div><dt class="text-xs text-ink-2">{t('refreshExpiry')}</dt><dd class="tabular-nums">{date(session.refresh_expires_at)}</dd></div>
            <div><dt class="text-xs text-ink-2">{t('project')}</dt><dd class="font-mono break-all">{session.project_id || t('unknown')}</dd></div>
            <div><dt class="text-xs text-ink-2">{t('device')}</dt><dd>{session.device_type && session.device_type !== 'unknown' ? session.device_type : t('unknown')} · {session.os || t('unknown')}</dd></div>
            <div><dt class="text-xs text-ink-2">{t('method')}</dt><dd>{session.auth_method === 'password' ? t('password') : session.auth_method === 'federated' ? t('federated') : t('unknown')}</dd></div>
          </dl></Card>
        {/each}
      </div>
    </section>
    <section class="mt-6 space-y-3" aria-label={t('recent')}>
      <h2 class="text-sm font-semibold">{t('recent')}</h2><p class="text-sm text-ink-2">{t('recentNotice')}</p>
      {#if data.history.events?.length === 0}<p class="text-sm text-ink-2">{t('emptyEvents')}</p>{/if}
      {#if data.history.events?.length}<TableShell><table><thead><tr><th>{t('timestamp')}</th><th>{t('action')}</th><th>{t('status')}</th><th>{t('project')}</th><th>{t('method')}</th></tr></thead><tbody>
        {#each data.history.events as event}<tr><td class="tabular-nums">{date(event.at)}</td><td>{event.resource_type} · {event.action}</td><td>{event.status === 'success' ? t('success') : event.status === 'failed' ? t('failed') : event.status === 'started' ? t('startedStatus') : event.status}</td><td class="font-mono">{event.project_id}</td><td>{event.auth_method === 'password' ? t('password') : event.auth_method === 'federated' ? t('federated') : t('unknown')}</td></tr>{/each}
      </tbody></table></TableShell>{/if}
    </section>
  {/if}
</PageShell>
