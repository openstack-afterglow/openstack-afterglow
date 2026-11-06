<script lang="ts">
	import { createObservationView } from '$lib/components/admin/observation/observationView.svelte';
	import ObservationTable from '$lib/components/admin/observation/ObservationTable.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { domainsApi } from '$lib/api/domains';
  import type { DomainMonitoring, DomainWindow, ObservationState } from '$lib/api/domains';
  import { ApiError } from '$lib/api/client';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import TableShell from '$lib/components/ui/TableShell.svelte';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
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
  let snapshotScope = ''; 
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
    const ownerScope = `${id}:${selectedWindow}`;
    let alive = true;
    untrack(() => { if (!token || snapshotScope !== ownerScope) data = null; snapshotScope = ownerScope; error = ''; loading = true; });
    domainsApi.monitoring(id, selectedWindow, { token, projectId }).then(response => {
      if (!alive || id !== domainId || token !== ($auth.token ?? undefined) || projectId !== ($auth.projectId ?? undefined)) return;
      if (response.domain.id !== id) { error = t('scope.invalid'); return; }
      data = response;
    }).catch(reason => {
      if (alive) error = reason instanceof ApiError ? reason.message : t('monitor.failed');
    }).finally(() => { if (alive) loading = false; });
    return () => { alive = false; };
  });
  const summaryRows = $derived(data ? [
    { key: 'users', statusKey: 'ready', raw: data.directory.users, label: t('monitor.users'), value: count(data.directory.users), status: t('state.available') },
    { key: 'projects', statusKey: 'ready', raw: data.directory.projects, label: t('monitor.projects'), value: count(data.directory.projects), status: t('state.available') },
    { key: 'requests', statusKey: data.requests.state, raw: data.requests.total, label: t('monitor.requests'), value: count(data.requests.total), status: stateLabel(data.requests.state) },
    { key: 'requestErrors', statusKey: data.requests.state, raw: data.requests.errors, label: t('monitor.requestErrors'), value: count(data.requests.errors), status: stateLabel(data.requests.state) },
    { key: 'loginSuccesses', statusKey: data.logins.state, raw: data.logins.successes, label: t('monitor.loginSuccesses'), value: count(data.logins.successes), status: stateLabel(data.logins.state) },
    { key: 'recordedFailures', statusKey: data.logins.state, raw: data.logins.recorded_failures, label: t('monitor.recordedFailures'), value: count(data.logins.recorded_failures), status: stateLabel(data.logins.state) },
    { key: 'failureHistory', statusKey: 'unavailable', raw: null, label: t('monitor.failureHistory'), value: t('monitor.notCollected'), status: t('state.unavailable') },
    { key: 'validSessions', statusKey: data.sessions.state, raw: data.sessions.valid_count, label: t('monitor.validSessions'), value: data.sessions.state === 'partial' && data.sessions.valid_count != null ? t('monitor.lowerBound', { value: count(data.sessions.valid_count) }) : count(data.sessions.valid_count), status: stateLabel(data.sessions.state) },
    { key: 'recentSessions', statusKey: data.sessions.state, raw: data.sessions.observed_recent_count, label: t('monitor.recentSessions'), value: count(data.sessions.observed_recent_count), status: stateLabel(data.sessions.state) },
    { key: 'unattributedSessions', statusKey: data.sessions.unattributed_count == null ? 'unavailable' : data.sessions.unattributed_count > 0 ? 'partial' : 'ready', raw: data.sessions.unattributed_count, label: t('monitor.unattributedSessions'), value: count(data.sessions.unattributed_count), status: data.sessions.unattributed_count == null ? t('state.unavailable') : data.sessions.unattributed_count > 0 ? t('state.partial') : t('state.available') },
    { key: 'online', statusKey: 'unavailable', raw: null, label: t('monitor.online'), value: count(data.sessions.online_count), status: t('state.unavailable') },
    { key: 'recentUsers', statusKey: data.activity.state, raw: data.activity.recent_users, label: t('monitor.recentUsers'), value: count(data.activity.recent_users), status: stateLabel(data.activity.state) },
    { key: 'events', statusKey: data.activity.state, raw: data.activity.events, label: t('monitor.events'), value: count(data.activity.events), status: stateLabel(data.activity.state) },
    { key: 'lastSeen', statusKey: data.activity.state, raw: data.activity.last_seen ? Date.parse(data.activity.last_seen) : null, label: t('monitor.lastSeen'), value: time(data.activity.last_seen), status: stateLabel(data.activity.state) },
  ] : []);

	const observationView0 = createObservationView(() => (summaryRows), () => ([{ key: 'metric', label: t('monitor.metric'), value: row => row.label, filterValues: row => [row.key], format: (_value, row) => row.label }, { key: 'value', label: t('monitor.value'), value: row => row.raw, format: (_value, row) => row.value }, { key: 'status', label: t('form.status'), value: row => row.status, filterValues: row => [row.statusKey], format: (_value, row) => row.status }]));
	const observationView1 = createObservationView(() => data?.resources ?? [], () => [
		{ key: 'service', label: t('monitor.service'), value: row => row.service },
		{ key: 'metric', label: t('monitor.metric'), value: row => row.metric },
		{ key: 'kind', label: t('monitor.kind'), value: row => row.kind },
		{ key: 'value', label: t('monitor.value'), value: row => row.value, format: (_value, row) => row.status === 'unlimited' ? t('state.unlimited') : row.status === 'partial' && row.error === 'owner_unavailable' && row.value != null ? t('monitor.lowerBound', { value: count(row.value) }) : count(row.value) },
		{ key: 'status', label: t('form.status'), value: row => row.status },
		{ key: 'reason', label: t('monitor.reason'), value: row => row.error },
	]);
	const observationView2 = createObservationView(() => data?.requests.services ?? [], () => [
		{ key: 'service', label: t('monitor.service'), value: row => row.service },
		{ key: 'requests', label: t('monitor.requests'), value: row => row.requests },
		{ key: 'errors', label: t('monitor.requestErrors'), value: row => row.errors },
	]);
	const observationView3 = createObservationView(() => data?.requests.timeline ?? [], () => [
		{ key: 'time', label: t('monitor.time'), value: row => row.at },
		{ key: 'requests', label: t('monitor.requests'), value: row => row.requests },
		{ key: 'errors', label: t('monitor.requestErrors'), value: row => row.errors },
	]);
	const observationView4 = createObservationView(() => data?.logins.timeline ?? [], () => [
		{ key: 'time', label: t('monitor.time'), value: row => row.at },
		{ key: 'success', label: t('monitor.loginSuccesses'), value: row => row.successes },
		{ key: 'failures', label: t('monitor.recordedFailures'), value: row => row.recorded_failures },
	]);
	const observationView5 = createObservationView(() => data?.activity.hour_distribution ?? [], () => [
		{ key: 'hour', label: t('monitor.utcHour'), value: row => row.hour },
		{ key: 'events', label: t('monitor.events'), value: row => row.events },
	]);
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
  {#if error}<Alert>{error}</Alert>{/if}
  {#if loading}<LoadingState variant="section" label={t('state.loading')} />{/if}
  {#if data}
    {@const monitoring = data}
    <Alert tone={data.coverage.partial ? 'warning' : 'info'} class="mb-4">
      {t('monitor.coverage')}: {data.coverage.partial ? t('state.partial') : t('state.available')}
      <span class="block mt-1">{t('monitor.observedAt')}: {time(data.coverage.observed_at)}</span>
      <span class="block mt-1">{t('monitor.notOnline')}</span>
    </Alert>
    <section class="mb-6" aria-labelledby="domain-observation-summary">
      <h2 id="domain-observation-summary" class="text-sm font-semibold text-ink-0 mb-3">{t('monitor.summary')}</h2>
      <ObservationTable model={observationView0}>
{#snippet children(tableView)}
<ResponsiveTable>
        {#snippet cards()}
          {#each tableView.rows as row (row.key)}
            <CompactResourceCard>
              <div class="flex flex-wrap items-start justify-between gap-2"><h3 class="text-sm font-medium text-ink-0">{row.label}</h3><Pill>{row.status}</Pill></div>
              <dl class="text-xs text-ink-2"><div class="flex flex-wrap justify-between gap-2"><dt>{t('monitor.value')}</dt><dd class="break-words tabular-nums">{row.value}</dd></div></dl>
            </CompactResourceCard>
          {/each}
        {/snippet}
        <TableShell><table><thead><tr><TableColumnHeader view={tableView} columnKey="metric" /><TableColumnHeader view={tableView} columnKey="value" /><TableColumnHeader view={tableView} columnKey="status" /></tr></thead><tbody>
          {#each tableView.rows as row (row.key)}<tr><td>{row.label}</td><td>{row.value}</td><td>{row.status}</td></tr>{/each}
        </tbody></table></TableShell>
      </ResponsiveTable>
{/snippet}
</ObservationTable>
    </section>
    <section class="mb-6" aria-labelledby="domain-resource-observations">
      <h2 id="domain-resource-observations" class="text-sm font-semibold text-ink-0 mb-3">{t('monitor.resources')}</h2>
      <p class="text-sm text-ink-2 mb-3">{t('monitor.resourceHelp')}</p>
      <ObservationTable model={observationView1}>
{#snippet children(tableView)}
<ResponsiveTable>
        {#snippet cards()}
          {#each tableView.rows as metric (`${metric.service}:${metric.metric}:${metric.kind}`)}
            <CompactResourceCard>
              <div class="flex flex-wrap items-start justify-between gap-2"><h3 class="min-w-0 break-all text-sm font-medium text-ink-0">{metric.metric}</h3><Pill>{stateLabel(metric.status)}</Pill></div>
              <dl class="grid gap-1 text-xs text-ink-2">
                <div class="flex flex-wrap justify-between gap-2"><dt>{t('monitor.service')}</dt><dd class="break-all">{metric.service}</dd></div>
                <div class="flex flex-wrap justify-between gap-2"><dt>{t('monitor.kind')}</dt><dd>{t(`kind.${metric.kind}`)}</dd></div>
                <div class="flex flex-wrap justify-between gap-2"><dt>{t('monitor.value')}</dt><dd class="break-words tabular-nums">{metric.status === 'unlimited' ? t('state.unlimited') : metric.status === 'partial' && metric.error === 'owner_unavailable' && metric.value != null ? t('monitor.lowerBound', { value: count(metric.value) }) : count(metric.value)}{metric.value != null ? ` ${metric.unit}` : ''}</dd></div>
              </dl>
              {#snippet details()}<dl class="text-xs text-ink-2"><div><dt>{t('monitor.reason')}</dt><dd class="break-all">{metric.error ?? '—'}</dd></div></dl>{/snippet}
            </CompactResourceCard>
          {/each}
        {/snippet}
      <TableShell><table><thead><tr><TableColumnHeader view={tableView} columnKey="service" /><TableColumnHeader view={tableView} columnKey="metric" /><TableColumnHeader view={tableView} columnKey="kind" /><TableColumnHeader view={tableView} columnKey="value" /><TableColumnHeader view={tableView} columnKey="status" /><TableColumnHeader view={tableView} columnKey="reason" /></tr></thead><tbody>
        {#each tableView.rows as metric (`${metric.service}:${metric.metric}:${metric.kind}`)}<tr>
          <td>{metric.service}</td><td>{metric.metric}</td><td>{t(`kind.${metric.kind}`)}</td>
          <td>{metric.status === 'unlimited' ? t('state.unlimited') : metric.status === 'partial' && metric.error === 'owner_unavailable' && metric.value != null ? t('monitor.lowerBound', { value: count(metric.value) }) : count(metric.value)}{metric.value != null ? ` ${metric.unit}` : ''}</td>
          <td><Pill>{stateLabel(metric.status)}</Pill></td><td>{metric.error ?? '—'}</td>
        </tr>{/each}
      </tbody></table></TableShell>
      </ResponsiveTable>
{/snippet}
</ObservationTable>
    </section>
    <section class="mb-6" aria-labelledby="domain-request-observations">
      <h2 id="domain-request-observations" class="text-sm font-semibold text-ink-0 mb-3">{t('monitor.requests')} · {stateLabel(data.requests.state)}</h2>
      <p class="text-sm text-ink-2 mb-3">{t('monitor.requestHelp')}</p>
      {#if data.requests.services.length === 0}<p class="text-sm text-ink-2">{t('monitor.noData')}</p>{/if}
        <ObservationTable model={observationView2}>
{#snippet children(tableView)}
<ResponsiveTable>
          {#snippet cards()}
            {#each tableView.rows as service (service.service)}
              <CompactResourceCard>
                <h3 class="break-all text-sm font-medium text-ink-0">{service.service}</h3>
                <dl class="grid gap-1 text-xs text-ink-2">
                  <div class="flex flex-wrap justify-between gap-2"><dt>{t('monitor.requests')}</dt><dd class="tabular-nums">{count(service.requests)}</dd></div>
                  <div class="flex flex-wrap justify-between gap-2"><dt>{t('monitor.requestErrors')}</dt><dd class="tabular-nums">{count(service.errors)}</dd></div>
                </dl>
              </CompactResourceCard>
            {/each}
          {/snippet}
        <TableShell><table><thead><tr><TableColumnHeader view={tableView} columnKey="service" /><TableColumnHeader view={tableView} columnKey="requests" /><TableColumnHeader view={tableView} columnKey="errors" /></tr></thead><tbody>
          {#each tableView.rows as service (service.service)}<tr><td>{service.service}</td><td>{count(service.requests)}</td><td>{count(service.errors)}</td></tr>{/each}
        </tbody></table></TableShell>
        </ResponsiveTable>
{/snippet}
</ObservationTable>
    </section>
    <div class="space-y-4">
      {#if data.requests.timeline}<details><summary class="text-sm text-ink-1 min-h-11 cursor-pointer">{t('monitor.requestTimeline')} · {stateLabel(data.requests.state)}</summary>
        <ObservationTable model={observationView3}>
{#snippet children(tableView)}
<ResponsiveTable>
          {#snippet cards()}
            {#each tableView.rows as row (row.at)}
              <CompactResourceCard>
                <h3 class="text-sm font-medium text-ink-0">{time(row.at)}</h3>
                <dl class="grid gap-1 text-xs text-ink-2">
                  <div class="flex flex-wrap justify-between gap-2"><dt>{t('monitor.requests')}</dt><dd class="tabular-nums">{count(row.requests)}</dd></div>
                  <div class="flex flex-wrap justify-between gap-2"><dt>{t('monitor.requestErrors')}</dt><dd class="tabular-nums">{count(row.errors)}</dd></div>
                </dl>
              </CompactResourceCard>
            {/each}
          {/snippet}
        <TableShell><table><thead><tr><TableColumnHeader view={tableView} columnKey="time" /><TableColumnHeader view={tableView} columnKey="requests" /><TableColumnHeader view={tableView} columnKey="errors" /></tr></thead><tbody>{#each tableView.rows as row (row.at)}<tr><td>{time(row.at)}</td><td>{count(row.requests)}</td><td>{count(row.errors)}</td></tr>{/each}</tbody></table></TableShell>
        </ResponsiveTable>
{/snippet}
</ObservationTable>
      </details>{/if}
      {#if data.logins.timeline}<details><summary class="text-sm text-ink-1 min-h-11 cursor-pointer">{t('monitor.loginTimeline')} · {stateLabel(data.logins.state)}</summary>
        <ObservationTable model={observationView4}>
{#snippet children(tableView)}
<ResponsiveTable>
          {#snippet cards()}
            {#each tableView.rows as row (row.at)}
              <CompactResourceCard>
                <h3 class="text-sm font-medium text-ink-0">{time(row.at)}</h3>
                <dl class="grid gap-1 text-xs text-ink-2">
                  <div class="flex flex-wrap justify-between gap-2"><dt>{t('monitor.loginSuccesses')}</dt><dd class="tabular-nums">{count(row.successes)}</dd></div>
                  <div class="flex flex-wrap justify-between gap-2"><dt>{t('monitor.recordedFailures')}</dt><dd class="tabular-nums">{count(row.recorded_failures)}</dd></div>
                </dl>
              </CompactResourceCard>
            {/each}
          {/snippet}
        <TableShell><table><thead><tr><TableColumnHeader view={tableView} columnKey="time" /><TableColumnHeader view={tableView} columnKey="success" /><TableColumnHeader view={tableView} columnKey="failures" /></tr></thead><tbody>{#each tableView.rows as row (row.at)}<tr><td>{time(row.at)}</td><td>{count(row.successes)}</td><td>{count(row.recorded_failures)}</td></tr>{/each}</tbody></table></TableShell>
        </ResponsiveTable>
{/snippet}
</ObservationTable>
      </details>{/if}
      {#if data.activity.hour_distribution}<details><summary class="text-sm text-ink-1 min-h-11 cursor-pointer">{t('monitor.activity')} · {stateLabel(data.activity.state)}</summary>
        <p class="text-sm text-ink-2 mb-3">{t('monitor.activityHelp')}</p>
        <ObservationTable model={observationView5}>
{#snippet children(tableView)}
<ResponsiveTable>
          {#snippet cards()}
            {#each tableView.rows as row (row.hour)}
              <CompactResourceCard>
                <h3 class="text-sm font-medium text-ink-0">{t('monitor.utcHour')}: {row.hour.toLocaleString(intlLocale())}</h3>
                <dl class="text-xs text-ink-2"><div class="flex flex-wrap justify-between gap-2"><dt>{t('monitor.events')}</dt><dd class="tabular-nums">{count(row.events)}</dd></div></dl>
              </CompactResourceCard>
            {/each}
          {/snippet}
        <TableShell><table><thead><tr><TableColumnHeader view={tableView} columnKey="hour" /><TableColumnHeader view={tableView} columnKey="events" /></tr></thead><tbody>{#each tableView.rows as row (row.hour)}<tr><td>{row.hour.toLocaleString(intlLocale())}</td><td>{count(row.events)}</td></tr>{/each}</tbody></table></TableShell>
        </ResponsiveTable>
{/snippet}
</ObservationTable>
      </details>{/if}
      <details><summary class="text-sm text-ink-1 min-h-11 cursor-pointer">{t('monitor.coverage')}</summary><ul class="list-disc pl-5 text-sm text-ink-2 space-y-2">{#each data.coverage.notes as note}<li>{note in noteKeys ? t(noteKeys[note as keyof typeof noteKeys]) : note}</li>{/each}</ul></details>
    </div>
  {/if}
</PageShell>
