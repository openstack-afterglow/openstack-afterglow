<script lang="ts">
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { domainsApi } from '$lib/api/domains';
  import type { DomainMonitoring, DomainWindow, ObservationState } from '$lib/api/domains';
  import { ApiError } from '$lib/api/client';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import TableShell from '$lib/components/ui/TableShell.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Pill from '$lib/components/ui/Pill.svelte';
  import SelectInput from '$lib/components/ui/SelectInput.svelte';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import { t } from '$lib/i18n/ns/domain-admin';
  let { domainId, domainName }: { domainId: string; domainName: string } = $props();
  let data = $state<DomainMonitoring | null>(null);
  let loading = $state(true);
  let error = $state('');
  let window = $state<DomainWindow>('24h');
  let revision = $state(0);
  const statusKeys = { ready: 'state.available', partial: 'state.partial', unavailable: 'state.unavailable', denied: 'state.denied', disabled: 'state.disabled', unlimited: 'state.unlimited' } as const;
  function stateLabel(state: ObservationState) { return t(statusKeys[state]); }
  function count(value: number | null | undefined) { return value == null ? t('state.unavailable') : value.toLocaleString(intlLocale()); }
  function time(value: string | null) { return value ? new Date(value).toLocaleString(intlLocale()) : t('monitor.noData'); }
  const noteKeys = {
    login_failure_history_not_collected: 'coverage.failureHistory',
    activity_is_afterglow_audit_only: 'coverage.activity',
    sessions_are_not_online_presence: 'coverage.online',
    activity_observation_limit_exceeded: 'coverage.limit',
    activity_storage_unavailable: 'coverage.storage',
    sessions_incomplete: 'coverage.sessions',
    sessions_without_domain_attribution: 'coverage.unattributed',
    resources_incomplete: 'coverage.resources',
    requests_token_attributed_partial: 'coverage.requests',
  } as const;
  $effect(() => {
    const id = domainId;
    const selectedWindow = window;
    const token = $auth.token ?? undefined;
    const projectId = $auth.projectId ?? undefined;
    revision;
    let alive = true;
    untrack(() => { data = null; error = ''; loading = true; });
    domainsApi.monitoring(id, selectedWindow, { token, projectId }).then(response => {
      if (!alive || id !== domainId || token !== ($auth.token ?? undefined) || projectId !== ($auth.projectId ?? undefined)) return;
      if (response.domain.id !== id) { error = t('scope.invalid'); return; }
      data = response;
    }).catch(reason => {
      if (alive) error = reason instanceof ApiError ? reason.message : t('monitor.failed');
    }).finally(() => { if (alive) loading = false; });
    return () => { alive = false; };
  });
</script>

<PageShell>
  <PageHeader title={`${t('monitor.title')} · ${domainName}`} breadcrumb={t('inventory.breadcrumb')}>
    {#snippet actions()}
      <SelectInput bind:value={window} ariaLabel={t('monitor.window')}>
        <option value="24h">{t('monitor.day')}</option><option value="7d">{t('monitor.week')}</option><option value="30d">{t('monitor.month')}</option>
      </SelectInput>
      <Button variant="secondary" disabled={loading} onclick={() => revision += 1}>{t('actions.refresh')}</Button>
      <Button variant="link" href={`/admin/users?domain_id=${encodeURIComponent(domainId)}`}>{t('monitor.manageUsers')}</Button>
    {/snippet}
  </PageHeader>
  {#if error}<Alert>{error}</Alert>
  {:else if loading}<p class="text-sm text-ink-2" role="status">{t('state.loading')}</p>
  {:else if data}
    <Alert tone={data.coverage.partial ? 'warning' : 'info'} class="mb-4">
      {t('monitor.coverage')}: {data.coverage.partial ? t('state.partial') : t('state.available')}
      <span class="block mt-1">{t('monitor.observedAt')}: {time(data.coverage.observed_at)}</span>
      <span class="block mt-1">{t('monitor.notOnline')}</span>
    </Alert>
    <section class="mb-6" aria-labelledby="domain-observation-summary">
      <h2 id="domain-observation-summary" class="text-sm font-semibold text-ink-0 mb-3">{t('monitor.summary')}</h2>
      <TableShell><table><thead><tr><th>{t('monitor.metric')}</th><th>{t('monitor.value')}</th><th>{t('form.status')}</th></tr></thead><tbody>
        <tr><td>{t('monitor.users')}</td><td>{count(data.directory.users)}</td><td>{t('state.available')}</td></tr>
        <tr><td>{t('monitor.projects')}</td><td>{count(data.directory.projects)}</td><td>{t('state.available')}</td></tr>
        <tr><td>{t('monitor.requests')}</td><td>{count(data.requests.total)}</td><td>{stateLabel(data.requests.state)}</td></tr>
        <tr><td>{t('monitor.requestErrors')}</td><td>{count(data.requests.errors)}</td><td>{stateLabel(data.requests.state)}</td></tr>
        <tr><td>{t('monitor.loginSuccesses')}</td><td>{count(data.logins.successes)}</td><td>{stateLabel(data.logins.state)}</td></tr>
        <tr><td>{t('monitor.recordedFailures')}</td><td>{count(data.logins.recorded_failures)}</td><td>{stateLabel(data.logins.state)}</td></tr>
        <tr><td>{t('monitor.failureHistory')}</td><td>{t('monitor.notCollected')}</td><td>{t('state.unavailable')}</td></tr>
        <tr><td>{t('monitor.validSessions')}</td><td>{data.sessions.state === 'partial' && data.sessions.valid_count != null ? t('monitor.lowerBound', { value: count(data.sessions.valid_count) }) : count(data.sessions.valid_count)}</td><td>{stateLabel(data.sessions.state)}</td></tr>
        <tr><td>{t('monitor.recentSessions')}</td><td>{count(data.sessions.observed_recent_count)}</td><td>{stateLabel(data.sessions.state)}</td></tr>
        <tr><td>{t('monitor.unattributedSessions')}</td><td>{count(data.sessions.unattributed_count)}</td><td>{data.sessions.unattributed_count == null ? t('state.unavailable') : data.sessions.unattributed_count > 0 ? t('state.partial') : t('state.available')}</td></tr>
        <tr><td>{t('monitor.online')}</td><td>{count(data.sessions.online_count)}</td><td>{t('state.unavailable')}</td></tr>
        <tr><td>{t('monitor.recentUsers')}</td><td>{count(data.activity.recent_users)}</td><td>{stateLabel(data.activity.state)}</td></tr>
        <tr><td>{t('monitor.events')}</td><td>{count(data.activity.events)}</td><td>{stateLabel(data.activity.state)}</td></tr>
        <tr><td>{t('monitor.lastSeen')}</td><td>{time(data.activity.last_seen)}</td><td>{stateLabel(data.activity.state)}</td></tr>
      </tbody></table></TableShell>
    </section>
    <section class="mb-6" aria-labelledby="domain-resource-observations">
      <h2 id="domain-resource-observations" class="text-sm font-semibold text-ink-0 mb-3">{t('monitor.resources')}</h2>
      <p class="text-sm text-ink-2 mb-3">{t('monitor.resourceHelp')}</p>
      <TableShell><table><thead><tr><th>{t('monitor.service')}</th><th>{t('monitor.metric')}</th><th>{t('monitor.kind')}</th><th>{t('monitor.value')}</th><th>{t('form.status')}</th><th>{t('monitor.reason')}</th></tr></thead><tbody>
        {#each data.resources as metric (`${metric.service}:${metric.metric}:${metric.kind}`)}<tr>
          <td>{metric.service}</td><td>{metric.metric}</td><td>{t(`kind.${metric.kind}`)}</td>
          <td>{metric.status === 'unlimited' ? t('state.unlimited') : metric.status === 'partial' && metric.error === 'owner_unavailable' && metric.value != null ? t('monitor.lowerBound', { value: count(metric.value) }) : count(metric.value)}{metric.value != null ? ` ${metric.unit}` : ''}</td>
          <td><Pill>{stateLabel(metric.status)}</Pill></td><td>{metric.error ?? '—'}</td>
        </tr>{/each}
      </tbody></table></TableShell>
    </section>
    <section class="mb-6" aria-labelledby="domain-request-observations">
      <h2 id="domain-request-observations" class="text-sm font-semibold text-ink-0 mb-3">{t('monitor.requests')} · {stateLabel(data.requests.state)}</h2>
      <p class="text-sm text-ink-2 mb-3">{t('monitor.requestHelp')}</p>
      {#if data.requests.services.length}
        <TableShell><table><thead><tr><th>{t('monitor.service')}</th><th>{t('monitor.requests')}</th><th>{t('monitor.requestErrors')}</th></tr></thead><tbody>
          {#each data.requests.services as service (service.service)}<tr><td>{service.service}</td><td>{count(service.requests)}</td><td>{count(service.errors)}</td></tr>{/each}
        </tbody></table></TableShell>
      {:else}<p class="text-sm text-ink-2">{t('monitor.noData')}</p>{/if}
    </section>
    <div class="space-y-4">
      {#if data.requests.timeline}<details><summary class="text-sm text-ink-1 min-h-11 cursor-pointer">{t('monitor.requestTimeline')} · {stateLabel(data.requests.state)}</summary>
        <TableShell><table><thead><tr><th>{t('monitor.time')}</th><th>{t('monitor.requests')}</th><th>{t('monitor.requestErrors')}</th></tr></thead><tbody>{#each data.requests.timeline as row (row.at)}<tr><td>{time(row.at)}</td><td>{count(row.requests)}</td><td>{count(row.errors)}</td></tr>{/each}</tbody></table></TableShell>
      </details>{/if}
      {#if data.logins.timeline}<details><summary class="text-sm text-ink-1 min-h-11 cursor-pointer">{t('monitor.loginTimeline')} · {stateLabel(data.logins.state)}</summary>
        <TableShell><table><thead><tr><th>{t('monitor.time')}</th><th>{t('monitor.loginSuccesses')}</th><th>{t('monitor.recordedFailures')}</th></tr></thead><tbody>{#each data.logins.timeline as row (row.at)}<tr><td>{time(row.at)}</td><td>{count(row.successes)}</td><td>{count(row.recorded_failures)}</td></tr>{/each}</tbody></table></TableShell>
      </details>{/if}
      {#if data.activity.hour_distribution}<details><summary class="text-sm text-ink-1 min-h-11 cursor-pointer">{t('monitor.activity')} · {stateLabel(data.activity.state)}</summary>
        <p class="text-sm text-ink-2 mb-3">{t('monitor.activityHelp')}</p>
        <TableShell><table><thead><tr><th>{t('monitor.utcHour')}</th><th>{t('monitor.events')}</th></tr></thead><tbody>{#each data.activity.hour_distribution as row (row.hour)}<tr><td>{row.hour.toLocaleString(intlLocale())}</td><td>{count(row.events)}</td></tr>{/each}</tbody></table></TableShell>
      </details>{/if}
      <details><summary class="text-sm text-ink-1 min-h-11 cursor-pointer">{t('monitor.coverage')}</summary><ul class="list-disc pl-5 text-sm text-ink-2 space-y-2">{#each data.coverage.notes as note}<li>{note in noteKeys ? t(noteKeys[note as keyof typeof noteKeys]) : note}</li>{/each}</ul></details>
    </div>
  {/if}
</PageShell>
