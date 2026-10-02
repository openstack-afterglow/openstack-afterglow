<script lang="ts">
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import type { Keypair } from '$lib/types/keypair';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import Modal from '$lib/components/ui/Modal.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
  import DockerfileLintPanel, { type DockerfileLintResponse } from '$lib/components/admin/libraries/DockerfileLintPanel.svelte';

  // ---------------------------------------------------------------------------
  // 타입
  // ---------------------------------------------------------------------------

  interface LayerBuild {
    id: number;
    layer_name: string;
    kind: string;
    python_version: string | null;
    share_id: string;
    server_id: string | null;
    port_id: string | null;
    build_token: string | null;
    cloud_init_status: string | null;
    status: string;
    progress_step: string;
    progress_pct: number;
    error_message: string | null;
    console_log_excerpt: string | null;
    started_at: string | null;
    completed_at: string | null;
    created_at: string | null;
    pip_packages?: string[];
    apt_packages?: string[];
    ubuntu_base: string;
    base_image_id?: string | null;
    base_image_name?: string | null;
    base_image_min_disk?: number | null;
    base_image_visibility?: string | null;
    parent_artifact_id?: number | null;
  }

  interface LayerBuildDetail extends LayerBuild {
    vm_status?: string | null;
    vm_ip?: string | null;
    live_console?: string | null;
  }


  interface LayerBaseImage {
    id: string;
    name: string;
    status: string;
    ubuntu_base: string;
    size: number;
    min_disk: number;
    min_ram: number;
    disk_format: string;
    visibility: string;
    owner: string;
    checksum: string | null;
    os_hash_algo: string | null;
    os_hash_value: string | null;
    created_at: string | null;
  }

  interface LayerImportJob {
    id: number;
    status: string;
    progress_step: string | null;
    progress_pct: number;
    error_message: string | null;
    github_url: string | null;
    commit_sha: string | null;
    dockerfile_path: string | null;
    layer_prefix: string;
    profile_name: string;
    ubuntu_base: string;
    base_image_id: string;
    base_image_name: string | null;
    planned_layers: { name: string; line: number; instruction: string }[];
    artifact_ids: number[];
    build_ids: number[];
    created_at: string | null;
    completed_at: string | null;
    source_type?: string;
    dockerfile_digest?: string | null;
    consume_id?: number | null;
    consumer_status?: string | null;
    consumer_spec?: { server_name?: string; flavor_id: string; network_id?: string; key_name?: string; ssh_public_key?: string; ssh_username?: string } | null;
  }

  interface LayerConsume {
    id: number;
    profile_name: string;
    server_id: string | null;
    port_id: string | null;
    server_name: string | null;
    share_id: string;
    status: string;
    error_message: string | null;
    created_at: string | null;
    completed_at: string | null;
    vm_status?: string | null;
    vm_ip?: string | null;
  }

  // ---------------------------------------------------------------------------
  // 상태
  // ---------------------------------------------------------------------------

  const TERMINAL = new Set(['complete', 'error', 'timeout', 'cancelled']);
  const CONSUME_BLOCKING_STATUSES = new Set(['creating', 'active', 'stopped', 'stop', 'shutoff', 'error']);

  const token = $derived($auth.token ?? undefined);
  const projectId = $derived($auth.projectId ?? undefined);

  let builds = $state<LayerBuild[]>([]);
  let consumes = $state<LayerConsume[]>([]);
  let baseImages = $state<LayerBaseImage[]>([]);
  let importJobs = $state<LayerImportJob[]>([]);
  let loading = $state(true);
  let error = $state('');
  let message = $state('');

  const activeBuilds = $derived(builds.filter(b => !TERMINAL.has(b.status)));
  const activeImportJobs = $derived(importJobs.filter(job => !TERMINAL.has(job.status)));

  // 프로필 구성 폼
  interface ArtifactSummary {
    id: number;
    name: string;
    kind: string;
    python_version: string | null;
    parent_id: number | null;
    is_sealed: boolean;
    is_published: boolean;
    pip_packages: string[];
    apt_packages: string[];
    ubuntu_base: string;
    base_image_id?: string | null;
    base_image_name?: string | null;
    base_image_min_disk?: number | null;
    base_image_visibility?: string | null;
    requested_packages: string[];
    created_at: string | null;
  }
  interface DeleteBlocker {
    type: string;
    message: string;
    items: Record<string, unknown>[];
  }
  interface LayerDeletePreview {
    artifact: ArtifactSummary;
    lineage: ArtifactSummary[];
    direct_children: ArtifactSummary[];
    child_count: number;
    profile_references: { id: number; name: string; layers: string[] }[];
    active_consume_references: { id: number; profile_name: string; status: string; server_id?: string | null }[];
    active_build_references: { id: number; layer_name: string; status: string }[];
    delete_blockers: DeleteBlocker[];
    can_delete: boolean;
  }
  interface LayerArtifact {
    id: number;
    name: string;
    kind: string;
    python_version: string | null;
    sqsh_filename: string;
    parent_id: number | null;
    is_sealed: boolean;
    is_published: boolean;
    created_at: string | null;
    pip_packages: string[];
    apt_packages: string[];
    ubuntu_base: string;
    base_image_id?: string | null;
    base_image_name?: string | null;
    base_image_min_disk?: number | null;
    base_image_visibility?: string | null;
    requested_packages: string[];
    lineage: ArtifactSummary[];
    ancestors: ArtifactSummary[];
    direct_children: ArtifactSummary[];
    child_count: number;
    profile_references: { id: number; name: string; layers: string[] }[];
    active_consume_references: { id: number; profile_name: string; status: string; server_id?: string | null }[];
    active_build_references: { id: number; layer_name: string; status: string }[];
    delete_blockers: DeleteBlocker[];
    can_delete: boolean;
  }
  interface LayerProfile { id: number; name: string; layers: string[]; is_published: boolean; created_at: string | null; updated_at: string | null; }
  let artifacts = $state<LayerArtifact[]>([]);
  let profiles = $state<LayerProfile[]>([]);
  let selectedProfileId = $state<number | null>(null);
  const selectedHistoricalProfile = $derived(profiles.find(profile => profile.id === selectedProfileId));
  let publicationUpdating = $state('');
  // 봉인 완료된 artifact만 부모 후보로 사용
  const sealedArtifacts = $derived(artifacts.filter(a => a.is_sealed));
  let profileMessage = $state('');
  let profileDeletingName = $state('');
  let profileDeleteError = $state('');


  let importForm = $state({ github_url: '', ref: '', dockerfile_path: 'Dockerfile', layer_prefix: '', profile_name: '' });
  let importSubmitting = $state(false);
  const pinnedCommitValid = $derived(/^[a-f0-9]{40}$/i.test(importForm.ref.trim()));
  type DockerfileExecutionTarget = 'build' | 'instance';
  const dockerfileTargetOptions = [
    { value: 'build', label: '레이어만 빌드' },
    { value: 'instance', label: '인스턴스까지 생성' },
  ];
  let dockerfileTarget = $state<DockerfileExecutionTarget>('build');
  let dockerfileConsumer = $state({ server_name: '', flavor_id: '', network_id: '', key_name: '', ssh_public_key: '', ssh_username: '' });
  const dockerfileConsumerReady = $derived(
    dockerfileTarget === 'build' || (
      !!dockerfileConsumer.flavor_id.trim() &&
      (!!dockerfileConsumer.key_name.trim() || !!dockerfileConsumer.ssh_public_key.trim())
    )
  );
  function buildDockerfileConsumer() {
    if (dockerfileTarget !== 'instance') return undefined;
    const consumer: Record<string, string> = { flavor_id: dockerfileConsumer.flavor_id.trim() };
    if (dockerfileConsumer.server_name.trim()) consumer.server_name = dockerfileConsumer.server_name.trim();
    if (dockerfileConsumer.network_id.trim()) consumer.network_id = dockerfileConsumer.network_id.trim();
    if (dockerfileConsumer.key_name) consumer.key_name = dockerfileConsumer.key_name;
    if (dockerfileConsumer.ssh_public_key.trim()) consumer.ssh_public_key = dockerfileConsumer.ssh_public_key.trim();
    if (dockerfileConsumer.ssh_username.trim()) consumer.ssh_username = dockerfileConsumer.ssh_username.trim();
    return consumer;
  }
  let selectedImportId = $state<number | null>(null);
  const selectedImport = $derived(importJobs.find(job => job.id === selectedImportId));
  let importLoadError = $state('');
  let historyConsumeTargetId = $state<number | null>(null);
  let historyConsumer = $state({ server_name: '', flavor_id: '', network_id: '', key_name: '', ssh_public_key: '', ssh_username: '' });
  let historyConsumeSubmitting = $state(false);
  let historyConsumeError = $state('');
  const historyConsumerReady = $derived(
    !!historyConsumer.flavor_id.trim() && (!!historyConsumer.key_name.trim() || !!historyConsumer.ssh_public_key.trim())
  );

  async function consumeCompletedImport(job: LayerImportJob) {
    if (historyConsumeSubmitting || job.status !== 'complete' || !job.dockerfile_digest || !historyConsumerReady || !job.artifact_ids?.length) return;
    historyConsumeSubmitting = true;
    historyConsumeError = '';
    try {
      const body: Record<string, string | number> = { import_id: job.id, flavor_id: historyConsumer.flavor_id.trim() };
      if (historyConsumer.server_name.trim()) body.server_name = historyConsumer.server_name.trim();
      if (historyConsumer.network_id.trim()) body.network_id = historyConsumer.network_id.trim();
      if (historyConsumer.key_name.trim()) body.key_name = historyConsumer.key_name.trim();
      if (historyConsumer.ssh_public_key.trim()) body.ssh_public_key = historyConsumer.ssh_public_key.trim();
      if (historyConsumer.ssh_username.trim()) body.ssh_username = historyConsumer.ssh_username.trim();
      const result = await api.post<{ consume_id: number; server_id: string }>('/api/v1/admin/libraries/consume', body, token, projectId);
      message = `작업 #${job.id}의 artifact로 VM ${result.server_id} 생성 완료`;
      historyConsumeTargetId = null;
      await loadConsumes(true);
    } catch (e) {
      historyConsumeError = e instanceof ApiError ? e.message : 'VM 생성에 실패했습니다';
    } finally {
      historyConsumeSubmitting = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Palimpsest Dockerfile 스튜디오 상태
  // ---------------------------------------------------------------------------
  type DockerfileInputMode = 'editor' | 'url' | 'upload' | 'github';
  const dockerfileModeOptions = [
    { value: 'editor', label: '직접 작성' },
    { value: 'url', label: 'URL 가져오기' },
    { value: 'upload', label: '파일 업로드' },
    { value: 'github', label: 'GitHub 커밋' },
  ];
  let dockerfileMode = $state<DockerfileInputMode>('editor');
  let dockerfileAuthoringRevision = 0;

  let dockerfileText = $state(`FROM ubuntu:24.04\nRUN apt-get update && apt-get install -y curl git\nENV APP_ENV=production\nWORKDIR /app\n`);
  let dockerfileUrl = $state('');
  let dockerfileFetching = $state(false);
  let dockerfileFetchError = $state('');
  let uploadedFileName = $state('');
  let dockerfileLint = $state<DockerfileLintResponse | null>(null);
  let lintLoading = $state(false);
  let lintError = $state('');
  let lintSeq = 0;

  async function runDockerfileLint(text: string, prefix: string, seq: number, requestToken: string, requestProjectId: string | undefined) {
    try {
      const body: Record<string, string> = { dockerfile: text };
      if (prefix) body.layer_prefix = prefix;
      const result = await api.post<DockerfileLintResponse>(
        '/api/v1/palimpsest/builds/dockerfile/lint', body, requestToken, requestProjectId,
      );
      if (seq === lintSeq) dockerfileLint = result;
    } catch (e) {
      if (seq === lintSeq) {
        dockerfileLint = null;
        lintError = e instanceof ApiError ? e.message : '네트워크 오류';
      }
    } finally {
      if (seq === lintSeq) lintLoading = false;
    }
  }

  $effect(() => {
    const text = dockerfileText;
    const prefix = importForm.layer_prefix.trim();
    const mode = dockerfileMode;
    const requestToken = token;
    const requestProjectId = projectId;
    const seq = ++lintSeq;
    dockerfileLint = null;
    lintError = '';
    const shouldLint = mode !== 'github' && !!text.trim() && !!requestToken;
    lintLoading = shouldLint;
    if (!shouldLint || !requestToken) return;
    const timer = setTimeout(() => { void runDockerfileLint(text, prefix, seq, requestToken, requestProjectId); }, 600);
    return () => clearTimeout(timer);
  });

  interface DockerfilePlanStep {
    name: string;
    instruction: string;
    args: string;
    step_digest?: string | null;
  }
  interface DockerfilePlanResponse {
    source_type: string;
    dockerfile_digest: string;
    parent_digest: string | null;
    ubuntu_base: string;
    cached_artifact_ids: number[];
    steps: DockerfilePlanStep[];
  }
  let dockerfilePlan = $state<DockerfilePlanResponse | null>(null);
  let planLoading = $state(false);
  let planError = $state('');
  let planSeq = 0;
  $effect(() => {
    // A plan belongs to this exact authoring input, never to a later edit.
    dockerfileText; importForm.layer_prefix; importForm.profile_name; dockerfileMode; token; projectId;
    ++planSeq;
    dockerfilePlan = null;
    planError = '';
    planLoading = false;
  });

  let keypairs = $state<Keypair[]>([]);


  // ---------------------------------------------------------------------------
  // 빌드 상세 모달
  // ---------------------------------------------------------------------------

  let detailOpen = $state(false);
  let selectedBuildId = $state<number | null>(null);
  let buildDetail = $state<LayerBuildDetail | null>(null);
  let detailLoading = $state(false);
  let detailCancelling = $state(false);
  let detailCancelError = $state('');

  const detailIsActive = $derived(buildDetail ? !TERMINAL.has(buildDetail.status) : false);

  // ---------------------------------------------------------------------------
  // 소비 상세 모달
  // ---------------------------------------------------------------------------

  let consumeDetailOpen = $state(false);
  let selectedConsumeId = $state<number | null>(null);
  let consumeDetail = $state<LayerConsume | null>(null);
  let consumeDetailLoading = $state(false);


  // ---------------------------------------------------------------------------
  // 아티팩트 삭제 모달
  // ---------------------------------------------------------------------------

  let deleteModalOpen = $state(false);
  let deletePreview = $state<LayerDeletePreview | null>(null);
  let deleteLoading = $state(false);
  let deleteSubmitting = $state(false);
  let deleteError = $state('');
  // ---------------------------------------------------------------------------
  // API 호출
  // ---------------------------------------------------------------------------

  async function loadBuilds(refresh = false) {
    try {
      builds = await api.get<LayerBuild[]>('/api/v1/admin/libraries/builds', token, projectId, { refresh });
    } catch { /* 무시 */ }
  }

  async function loadConsumes(refresh = false) {
    try {
      consumes = await api.get<LayerConsume[]>('/api/v1/admin/libraries/consumes', token, projectId, { refresh });
    } catch { /* 무시 */ }
  }

  async function loadArtifacts(refresh = false) {
    try {
      artifacts = await api.get<LayerArtifact[]>('/api/v1/admin/libraries/artifacts', token, projectId, { refresh });
    } catch { /* 무시 */ }
  }

  async function loadProfiles(refresh = false) {
    try {
      profiles = await api.get<LayerProfile[]>('/api/v1/admin/libraries/profiles', token, projectId, { refresh });
    } catch { /* 무시 */ }
  }

  async function loadBaseImages(refresh = false) {
    try {
      baseImages = await api.get<LayerBaseImage[]>('/api/v1/admin/libraries/base-images', token, projectId, { refresh });

    } catch {
      baseImages = [];
    }
  }

  async function loadImportJobs(refresh = true) {
    try {
      importJobs = await api.get<LayerImportJob[]>('/api/v1/admin/libraries/imports', token, projectId, { refresh });
      importLoadError = '';
    } catch {
      importLoadError = '작업 기록을 갱신하지 못했습니다. 새로고침으로 다시 시도하세요.';
    }
  }

  async function loadKeypairs(refresh = false) {
    try {
      keypairs = await api.get<Keypair[]>('/api/v1/keypairs', token, projectId, { refresh });
    } catch {
      keypairs = [];
    }
  }

  async function loadAll(refresh = false) {
    if (builds.length === 0 && consumes.length === 0) loading = true;
    error = '';
    await Promise.allSettled([loadBuilds(refresh), loadConsumes(refresh), loadArtifacts(refresh), loadProfiles(refresh), loadKeypairs(refresh), loadBaseImages(refresh), loadImportJobs(refresh)]);
    loading = false;
  }

  // 활성 빌드/Import job이 있으면 10초, 없으면 30초 폴링
  $effect(() => {
    const interval = setInterval(() => {
      void loadBuilds(true);
      void loadImportJobs();
      if (activeImportJobs.length > 0 || activeBuilds.length > 0) {
        void loadArtifacts(true);
        void loadProfiles(true);
        void loadConsumes(true);
      }
    }, activeBuilds.length > 0 || activeImportJobs.length > 0 ? 10_000 : 30_000);
    return () => clearInterval(interval);
  });

  $effect(() => {
    if (!token) return;
    untrack(() => loadAll());
  });



  function blockingConsumesForProfile(profileName: string): LayerConsume[] {
    return consumes.filter(
      consume => consume.profile_name === profileName
        && CONSUME_BLOCKING_STATUSES.has((consume.status || '').toLowerCase()),
    );
  }

  async function deleteProfile(profile: LayerProfile) {
    if (profileDeletingName) return;
    if (!window.confirm(`프로필 '${profile.name}'을 삭제할까요?`)) return;

    profileDeletingName = profile.name;
    profileDeleteError = '';
    profileMessage = '';
    try {
      await api.delete<{ deleted: boolean }>(
        `/api/v1/admin/libraries/profiles/${encodeURIComponent(profile.name)}`,
        token,
        projectId,
      );
      profileMessage = `프로필 '${profile.name}' 삭제 완료`;
      await Promise.allSettled([loadProfiles(true), loadConsumes(true), loadArtifacts(true)]);
    } catch (e) {
      if (e instanceof ApiError) {
        let detailMessage = e.message;
        if (e.status === 409) {
          try {
            const parsed = JSON.parse(e.message) as { message?: unknown };
            if (typeof parsed.message === 'string') detailMessage = parsed.message;
          } catch {
            // JSON payload이 아니면 ApiError.message 그대로 표시한다.
          }
        }
        profileDeleteError = `프로필 삭제 실패: ${detailMessage}`;
      } else {
        profileDeleteError = '네트워크 오류';
      }
    } finally {
      profileDeletingName = '';
    }
  }

  async function setProfilePublication(profile: LayerProfile, is_published: boolean) {
    const key = `profile:${profile.name}`;
    if (publicationUpdating) return;
    publicationUpdating = key;
    profileMessage = '';
    profileDeleteError = '';
    try {
      await api.patch<LayerProfile>(
        `/api/v1/admin/libraries/profiles/${encodeURIComponent(profile.name)}/publication`,
        { is_published },
        token,
        projectId,
      );
      profileMessage = `프로필 '${profile.name}' ${is_published ? '공개' : '비공개'} 전환 완료`;
      await loadProfiles(true);
    } catch (e) {
      profileDeleteError = e instanceof ApiError ? `공개 상태 변경 실패: ${e.message}` : '네트워크 오류';
    } finally {
      publicationUpdating = '';
    }
  }

  async function setArtifactPublication(artifact: LayerArtifact, is_published: boolean) {
    const key = `artifact:${artifact.id}`;
    if (publicationUpdating) return;
    publicationUpdating = key;
    error = '';
    message = '';
    try {
      await api.patch<LayerArtifact>(
        `/api/v1/admin/libraries/artifacts/${artifact.id}/publication`,
        { is_published },
        token,
        projectId,
      );
      message = `artifact #${artifact.id} ${is_published ? '공개' : '비공개'} 전환 완료`;
      await loadArtifacts(true);
    } catch (e) {
      error = e instanceof ApiError ? `공개 상태 변경 실패: ${e.message}` : '네트워크 오류';
    } finally {
      publicationUpdating = '';
    }
  }


  async function submitDockerfileImport() {
    if (importSubmitting || !pinnedCommitValid || !importForm.github_url.trim() || !importForm.layer_prefix.trim() || !dockerfileConsumerReady) return;
    importSubmitting = true;
    error = '';
    message = '';
    try {
      const body: Record<string, unknown> = {
        github_url: importForm.github_url.trim(),
        dockerfile_path: importForm.dockerfile_path.trim() || 'Dockerfile',
        layer_prefix: importForm.layer_prefix.trim(),
      };
      if (importForm.ref.trim()) body.ref = importForm.ref.trim();
      if (importForm.profile_name.trim()) body.profile_name = importForm.profile_name.trim();
      const consumer = buildDockerfileConsumer();
      if (consumer) body.consumer = consumer;
      const result = await api.post<LayerImportJob>('/api/v1/admin/libraries/imports/dockerfile', body, token, projectId);
      importJobs = [result, ...importJobs.filter(job => job.id !== result.id)];
      selectedImportId = result.id;
      message = `Dockerfile import 시작 (ID: ${result.id}, profile: ${result.profile_name})`;
      await Promise.allSettled([loadImportJobs(true), loadBuilds(true), loadConsumes(true), loadArtifacts(true), loadProfiles(true)]);
    } catch (e) {
      error = e instanceof ApiError ? `Dockerfile import 실패: ${e.message}` : '네트워크 오류';
    } finally {
      importSubmitting = false;
    }
  }


  async function fetchDockerfileFromUrl() {
    const targetUrl = dockerfileUrl.trim();
    if (!targetUrl || dockerfileFetching) return;
    const revision = ++dockerfileAuthoringRevision;
    dockerfileFetching = true;
    dockerfileFetchError = '';
    try {
      const res = await api.post<{ dockerfile: string; url: string; filename: string; size_bytes: number }>(
        '/api/v1/palimpsest/builds/dockerfile/fetch-url',
        { url: targetUrl },
        token,
        projectId,
      );
      if (revision !== dockerfileAuthoringRevision || dockerfileMode !== 'url' || dockerfileUrl.trim() !== targetUrl) return;
      dockerfileText = res.dockerfile;
      uploadedFileName = res.filename;
      dockerfileMode = 'editor';
      dockerfilePlan = null;
      planError = '';
      if (!importForm.layer_prefix) {
        const cleanName = res.filename.replace(/^Dockerfile\.?/i, '').replace(/[^a-z0-9]/gi, '').toLowerCase();
        importForm.layer_prefix = cleanName ? `${cleanName}-layer` : 'custom-layer';
      }
      message = `URL에서 Dockerfile을 성공적으로 불러왔습니다 (${res.filename}, ${res.size_bytes} bytes).`;
    } catch (e) {
      if (revision === dockerfileAuthoringRevision && dockerfileMode === 'url') {
        dockerfileFetchError = e instanceof ApiError ? e.message : 'URL에서 Dockerfile을 가져오지 못했습니다';
      }
    } finally {
      if (revision === dockerfileAuthoringRevision) dockerfileFetching = false;
    }
  }

  function handleDockerFileUpload(event: Event) {
    const input = event.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];
    const revision = ++dockerfileAuthoringRevision;
    dockerfileFetchError = '';
    const reader = new FileReader();
    reader.onload = (e) => {
      if (revision !== dockerfileAuthoringRevision || dockerfileMode !== 'upload') return;
      const text = e.target?.result;
      if (typeof text === 'string') {
        dockerfileText = text;
        uploadedFileName = file.name;
        dockerfileMode = 'editor';
        dockerfilePlan = null;
        planError = '';
        if (!importForm.layer_prefix) {
          const cleanName = file.name.replace(/^Dockerfile\.?/i, '').replace(/[^a-z0-9]/gi, '').toLowerCase();
          importForm.layer_prefix = cleanName ? `${cleanName}-layer` : 'custom-layer';
        }
        message = `로컬 파일 '${file.name}'을(를) 불러왔습니다.`;
      }
    };
    reader.onerror = () => {
      if (revision === dockerfileAuthoringRevision && dockerfileMode === 'upload') {
        dockerfileFetchError = '파일을 읽는 중 오류가 발생했습니다.';
      }
    };
    reader.readAsText(file);
  }

  async function previewDockerfilePlan() {
    if (planLoading || lintLoading || dockerfileLint?.valid === false) return;
    const seq = ++planSeq;
    planLoading = true;
    planError = '';
    dockerfilePlan = null;
    try {
      const body: Record<string, string> = {
        dockerfile: dockerfileText,
        layer_prefix: importForm.layer_prefix.trim() || 'demo',
      };
      if (importForm.profile_name.trim()) body.profile_name = importForm.profile_name.trim();

      const res = await api.post<DockerfilePlanResponse>(
        '/api/v1/palimpsest/builds/dockerfile/plan',
        body,
        token,
        projectId,
      );
      if (seq === planSeq) dockerfilePlan = res;
    } catch (e) {
      if (seq === planSeq) planError = e instanceof ApiError ? e.message : '빌드 계획을 생성하지 못했습니다';
    } finally {
      if (seq === planSeq) planLoading = false;
    }
  }

  async function submitInlineDockerfileBuild() {
    if (importSubmitting || lintLoading || dockerfileLint?.valid === false || !dockerfileConsumerReady) return;
    if (!dockerfileText.trim()) {
      error = 'Dockerfile 본문이 비어 있습니다';
      return;
    }
    if (!importForm.layer_prefix.trim()) {
      error = 'Layer prefix를 입력하세요';
      return;
    }
    importSubmitting = true;
    error = '';
    message = '';
    try {
      const body: Record<string, unknown> = {
        dockerfile: dockerfileText,
        layer_prefix: importForm.layer_prefix.trim(),
      };
      if (importForm.profile_name.trim()) body.profile_name = importForm.profile_name.trim();
      const consumer = buildDockerfileConsumer();
      if (consumer) body.consumer = consumer;

      const result = await api.post<LayerImportJob>(
        '/api/v1/palimpsest/builds/dockerfile',
        body,
        token,
        projectId,
      );
      importJobs = [result, ...importJobs.filter(job => job.id !== result.id)];
      selectedImportId = result.id;
      message = `Palimpsest Dockerfile 빌드 시작 (ID: ${result.id}, profile: ${result.profile_name})`;
      dockerfilePlan = null;
      await Promise.allSettled([loadImportJobs(true), loadBuilds(true), loadConsumes(true), loadArtifacts(true), loadProfiles(true)]);
    } catch (e) {
      error = e instanceof ApiError ? `Dockerfile 빌드 시작 실패: ${e.message}` : '네트워크 오류';
    } finally {
      importSubmitting = false;
    }
  }


  // ---------------------------------------------------------------------------
  // 빌드 상세 모달
  // ---------------------------------------------------------------------------

  async function openBuildDetail(build: LayerBuild) {
    selectedBuildId = build.id;
    detailOpen = true;
    buildDetail = null;
    detailCancelError = '';
  }

  async function loadBuildDetail() {
    if (!selectedBuildId) return;
    detailLoading = true;
    try {
      buildDetail = await api.get<LayerBuildDetail>(
        `/api/v1/admin/libraries/builds/${selectedBuildId}`,
        token,
        projectId,
        { refresh: true },
      );
    } catch { /* 이전 값 유지 */ } finally {
      detailLoading = false;
    }
  }

  async function cancelBuild() {
    if (!selectedBuildId || detailCancelling) return;
    detailCancelling = true;
    detailCancelError = '';
    try {
      await api.post(`/api/v1/admin/libraries/builds/${selectedBuildId}/cancel`, {}, token, projectId);
      await Promise.allSettled([loadBuildDetail(), loadBuilds(true)]);
    } catch (e) {
      detailCancelError = e instanceof ApiError ? e.message : '취소 실패';
    } finally {
      detailCancelling = false;
    }
  }

  $effect(() => {
    if (detailOpen && selectedBuildId) {
      loadBuildDetail();
    } else {
      buildDetail = null;
    }
  });

  $effect(() => {
    if (!detailOpen || !selectedBuildId) return;
    const interval = setInterval(() => {
      if (detailIsActive) loadBuildDetail();
    }, 10_000);
    return () => clearInterval(interval);
  });

  // ---------------------------------------------------------------------------
  // 소비 상세 모달
  // ---------------------------------------------------------------------------

  async function openConsumeDetail(c: LayerConsume) {
    selectedConsumeId = c.id;
    consumeDetailOpen = true;
    consumeDetail = null;
  }

  async function loadConsumeDetail() {
    if (!selectedConsumeId) return;
    consumeDetailLoading = true;
    try {
      consumeDetail = await api.get<LayerConsume>(
        `/api/v1/admin/libraries/consumes/${selectedConsumeId}`,
        token,
        projectId,
        { refresh: true },
      );
    } catch { /* 무시 */ } finally {
      consumeDetailLoading = false;
    }
  }

  $effect(() => {
    if (consumeDetailOpen && selectedConsumeId) {
      loadConsumeDetail();
    } else {
      consumeDetail = null;
    }
  });

  // ---------------------------------------------------------------------------
  // 아티팩트 삭제
  // ---------------------------------------------------------------------------

  async function openDeletePreview(artifact: LayerArtifact) {
    deleteModalOpen = true;
    deletePreview = null;
    deleteError = '';
    deleteLoading = true;
    try {
      deletePreview = await api.get<LayerDeletePreview>(
        `/api/v1/admin/libraries/artifacts/${artifact.id}/delete-preview`,
        token,
        projectId,
        { refresh: true },
      );
    } catch (e) {
      deleteError = e instanceof ApiError ? e.message : '삭제 미리보기 조회 실패';
    } finally {
      deleteLoading = false;
    }
  }

  async function executeDeleteArtifact() {
    if (!deletePreview?.can_delete || deleteSubmitting) return;
    deleteSubmitting = true;
    deleteError = '';
    try {
      await api.delete(`/api/v1/admin/libraries/artifacts/${deletePreview.artifact.id}`, token, projectId);
      message = `artifact #${deletePreview.artifact.id} (${deletePreview.artifact.name}) 삭제 완료`;
      deleteModalOpen = false;
      deletePreview = null;
      await Promise.allSettled([loadArtifacts(true), loadProfiles(true)]);
    } catch (e) {
      deleteError = e instanceof ApiError ? e.message : '삭제 실패';
    } finally {
      deleteSubmitting = false;
    }
  }

  // ---------------------------------------------------------------------------
  // 유틸
  // ---------------------------------------------------------------------------

  function fmtRelative(iso: string | null | undefined): string {
    if (!iso) return '—';
    const utcIso = iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z';
    const ms = Date.now() - new Date(utcIso).getTime();
    const s = Math.floor(ms / 1000);
    if (s < 60) return `${s}초 전`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}분 전`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}시간 전`;
    return `${Math.floor(h / 24)}일 전`;
  }

  // timezone 없는 ISO 문자열을 UTC로 강제 해석 (서버가 naive datetime을 반환할 경우 대비)
  function parseISO(iso: string): Date {
    const hasZone = iso.endsWith('Z') || iso.includes('+') || /[+-]\d{2}:\d{2}$/.test(iso);
    return new Date(hasZone ? iso : iso + 'Z');
  }

  function normalizeUbuntuBase(value: string | null | undefined): string {
    if (!value || value === 'ubuntu-24.04-server-2026-04-15') return 'ubuntu-24.04';
    return value;
  }

  function fmtDate(iso: string | null | undefined): string {
    if (!iso) return '—';
    return parseISO(iso).toLocaleString('ko-KR');
  }

  function elapsed(started: string | null | undefined): string {
    if (!started) return '—';
    const ms = Date.now() - parseISO(started).getTime();
    const s = Math.floor(ms / 1000);
    if (s < 60) return `${s}초`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}분 ${s % 60}초`;
    return `${Math.floor(m / 60)}시간 ${m % 60}분`;
  }


  function artifactChainLabel(artifact: LayerArtifact | ArtifactSummary): string {
    const chain = 'lineage' in artifact && artifact.lineage?.length
      ? artifact.lineage
      : [artifact as ArtifactSummary];
    return chain.map(a => `${a.name}#${a.id}`).join(' → ');
  }

  function ubuntuBaseText(base: string | null | undefined): string {
    const normalized = normalizeUbuntuBase(base);
    if (normalized === 'ubuntu-18.04') return 'Ubuntu 18.04';
    if (normalized === 'ubuntu-20.04') return 'Ubuntu 20.04';
    if (normalized === 'ubuntu-22.04') return 'Ubuntu 22.04';
    if (normalized === 'ubuntu-24.04') return 'Ubuntu 24.04';
    return normalized;
  }

  function baseImageForId(id: string | null | undefined): LayerBaseImage | null {
    return baseImages.find(image => image.id === id) ?? null;
  }

  function shortId(id: string | null | undefined): string {
    return id ? `${id.slice(0, 8)}…` : '—';
  }

  function baseImageLabel(image: LayerBaseImage): string {
    return `${image.name} · ${ubuntuBaseText(image.ubuntu_base)} · ${shortId(image.id)} · min ${image.min_disk || 0}GB · ${image.visibility}`;
  }

  function artifactBaseImageLabel(item: { ubuntu_base?: string | null; base_image_id?: string | null; base_image_name?: string | null; base_image_min_disk?: number | null; base_image_visibility?: string | null }): string {
    const image = baseImageForId(item.base_image_id ?? null);
    if (image) return baseImageLabel(image);
    if (item.base_image_id) return `${item.base_image_name || shortId(item.base_image_id)} · ${ubuntuBaseText(item.ubuntu_base)} · ${shortId(item.base_image_id)}${item.base_image_min_disk ? ` · min ${item.base_image_min_disk}GB` : ''}${item.base_image_visibility ? ` · ${item.base_image_visibility}` : ''}`;
    return ubuntuBaseText(item.ubuntu_base);
  }

  function ubuntuBaseLabel(item: { ubuntu_base?: string | null }): string {
    return ubuntuBaseText(item.ubuntu_base);
  }
  function packageLabel(artifact: LayerArtifact | ArtifactSummary): string {
    if (artifact.kind === 'system' || artifact.kind === 'nvidia') {
      const prefix = artifact.kind === 'nvidia' ? 'nvidia' : 'apt';
      return artifact.apt_packages?.length ? `${prefix}: ${artifact.apt_packages.join(', ')}` : '—';
    }
    const packages = artifact.requested_packages?.length ? artifact.requested_packages : artifact.pip_packages;
    return packages?.length ? `pip: ${packages.join(', ')}` : '—';
  }

  function buildPackageLabel(build: LayerBuild): string {
    if (build.kind === 'system') {
      return build.apt_packages?.length ? `apt: ${build.apt_packages.join(', ')}` : '—';
    }
    if (build.kind === 'nvidia') {
      return build.apt_packages?.length ? `nvidia: ${build.apt_packages.join(', ')}` : 'nvidia driver hook';
    }
    return build.pip_packages?.length ? `pip: ${build.pip_packages.join(', ')}` : '—';
  }

</script>

<div class="flex flex-col h-full overflow-auto bg-surface-base text-ink-1 p-6">
  <div data-tour="admin-library-header">
    <PageHeader title="Palimpsest 레이어 관리" breadcrumb="Palimpsest" subtitle="Dockerfile로 루트 레이어를 빌드하고 선택적으로 SSH VM을 생성합니다. 기존 기록도 이곳에서 조회합니다.">
      {#snippet actions()}
        <Button variant="secondary" href="/palimpsest/packages">프로젝트 패키지 / 접근 키</Button>
        <TutorialStartButton tour="admin-library" compactOnMobile />
        <button
          onclick={() => loadAll(true)}
          class="text-xs text-ink-2 hover:text-ink-0 transition-colors px-3 py-1.5 rounded border border-line-2 hover:border-line-2"
        >새로고침</button>
      {/snippet}
    </PageHeader>
  </div>
  <div class="mb-5 grid grid-cols-2 md:grid-cols-4 border-y border-line py-3" aria-label="Palimpsest 현황">
    <div class="px-3 first:pl-0 md:border-r md:border-line">
      <p class="text-xs text-ink-2">봉인된 레이어</p>
      <p class="mt-1 text-lg font-semibold tabular-nums text-ink-0">{sealedArtifacts.length}</p>
    </div>
    <div class="px-3 md:border-r md:border-line">
      <p class="text-xs text-ink-2">저장된 프로필</p>
      <p class="mt-1 text-lg font-semibold tabular-nums text-ink-0">{profiles.length}</p>
    </div>
    <div class="px-3 border-t border-line pt-3 md:border-t-0 md:border-r md:pt-0">
      <p class="text-xs text-ink-2">진행 중인 빌드</p>
      <p class="mt-1 text-lg font-semibold tabular-nums text-warm-text">{activeBuilds.length + activeImportJobs.length}</p>
    </div>
    <div class="px-3 border-t border-line pt-3 md:border-t-0 md:pt-0">
      <p class="text-xs text-ink-2">실행 중인 VM</p>
      <p class="mt-1 text-lg font-semibold tabular-nums text-state-success">{consumes.filter((consume) => CONSUME_BLOCKING_STATUSES.has((consume.status || '').toLowerCase())).length}</p>
    </div>
  </div>

  {#if error}
    <Alert tone="danger" class="mb-4">{error}</Alert>
  {/if}
  {#if message}
    <Alert tone="success" class="mb-4">{message}</Alert>
  {/if}

  {#if loading}
    <LoadingSkeleton rows={4} />
  {:else}
    <div class="mb-8" data-tour="admin-library-ready">
      <section class="min-w-0 bg-surface-raised border border-line rounded-lg p-5" data-tour="admin-library-import">
        <div class="flex items-center justify-between mb-1">
          <h2 class="text-sm font-semibold text-ink-0">Palimpsest Dockerfile 빌드</h2>
          <span class="text-xs px-2 py-0.5 rounded bg-surface-base border border-line-2 text-ink-2 font-mono">관리자 전용</span>
        </div>
        <p class="text-xs text-ink-2 mb-3">
          URL, 파일 업로드, 직접 작성으로 Dockerfile을 가져와 squashfs 레이어로 빌드하고 즉시 소비 인스턴스로 실행합니다.
        </p>

        <!-- 모드 선택 탭 -->
        <ToggleGroup
          value={dockerfileMode}
          options={dockerfileModeOptions}
          onchange={(value) => {
            ++dockerfileAuthoringRevision;
            dockerfileFetching = false;
            dockerfileMode = value as DockerfileInputMode;
          }}
          size="sm"
          fullWidth
          ariaLabel="Dockerfile 입력 방식"
          class="mb-4"
        />

        <div class="space-y-3">
          {#if dockerfileMode === 'url'}
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="dockerfile-fetch-url">Dockerfile URL *</label>
              <div class="flex gap-2">
                <input
                  id="dockerfile-fetch-url"
                  type="url"
                  placeholder="https://.../Dockerfile 또는 GitHub blob URL"
                  bind:value={dockerfileUrl}
                  oninput={() => { ++dockerfileAuthoringRevision; dockerfileFetching = false; }}
                  class="flex-1 bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
                />
                <button
                  type="button"
                  onclick={fetchDockerfileFromUrl}
                  disabled={dockerfileFetching || !dockerfileUrl.trim()}
                  class="px-3 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 disabled:cursor-not-allowed text-action-on-warm text-xs font-medium rounded-lg transition-colors whitespace-nowrap"
                >
                  {dockerfileFetching ? '가져오는 중...' : '가져오기'}
                </button>
              </div>
              {#if dockerfileFetchError}
                <Alert tone="danger" class="mt-2">{dockerfileFetchError}</Alert>
              {:else}
                <p class="mt-1 text-xs text-ink-2">GitHub blob, GitLab raw, 일반 HTTP/HTTPS URL을 지원합니다 (SSRF 보호 적용).</p>
              {/if}
            </div>
          {/if}

          {#if dockerfileMode === 'upload'}
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="dockerfile-file-upload">로컬 Dockerfile 선택 *</label>
              <div class="border-2 border-dashed border-line-2 hover:border-action-warm rounded-lg p-4 text-center bg-surface-base transition-colors">
                <input
                  id="dockerfile-file-upload"
                  type="file"
                  accept=".dockerfile,Dockerfile,text/*"
                  onchange={handleDockerFileUpload}
                  class="block w-full text-xs text-ink-2 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-surface-selected file:text-ink-0 hover:file:bg-surface-selected/80 cursor-pointer"
                />
                {#if uploadedFileName}
                  <p class="mt-2 text-xs text-warm-text font-mono">선택된 파일: {uploadedFileName}</p>
                {:else}
                  <p class="mt-2 text-xs text-ink-2">로컬 PC의 Dockerfile 파일을 선택하세요.</p>
                {/if}
              </div>
            </div>
          {/if}

          {#if dockerfileMode === 'editor' || (dockerfileMode !== 'github' && dockerfileText)}
            <div>
              <div class="flex items-center justify-between mb-1">
                <label class="block text-xs text-ink-2" for="dockerfile-editor-text">
                  Dockerfile 본문 {uploadedFileName ? `(${uploadedFileName})` : ''} *
                </label>
              </div>
              <textarea
                id="dockerfile-editor-text"
                rows="6"
                bind:value={dockerfileText}
                oninput={() => ++dockerfileAuthoringRevision}
                placeholder="FROM ubuntu:24.04&#10;RUN apt-get update && apt-get install -y curl&#10;ENV APP_ENV=production&#10;WORKDIR /app"
                class="w-full bg-surface-base border border-line-2 rounded-lg p-2.5 text-xs text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm font-mono resize-y"
              ></textarea>
              <p class="mt-0.5 text-xs text-ink-2">지원 문법: FROM, RUN, ENV, WORKDIR (COPY/ADD는 빌드 컨텍스트가 없으므로 GitHub 커밋 모드 사용). FROM은 ubuntu:18.04|20.04|22.04|24.04, Glance 이미지 이름/UUID, palimpsest/&lt;name&gt;@sha256:…를 지원하며 Glance에서 자동 해석됩니다.</p>
            </div>
          {/if}
          {#if dockerfileMode === 'upload' && dockerfileFetchError}<Alert tone="danger">{dockerfileFetchError}</Alert>{/if}

          {#if dockerfileMode === 'github'}
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="dockerfile-github-url">GitHub URL *</label>
              <input
                id="dockerfile-github-url"
                type="url"
                placeholder="https://github.com/org/repo"
                bind:value={importForm.github_url}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
              />
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label class="block text-xs text-ink-2 mb-1" for="dockerfile-ref">Commit SHA *</label>
                <input
                  id="dockerfile-ref"
                  type="text"
                  placeholder="40자 commit SHA 필수"
                  bind:value={importForm.ref}
                  class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
                />
              </div>
              <div>
                <label class="block text-xs text-ink-2 mb-1" for="dockerfile-path">Dockerfile path</label>
                <input
                  id="dockerfile-path"
                  type="text"
                  bind:value={importForm.dockerfile_path}
                  class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
                />
              </div>
            </div>
            <p class="text-xs text-ink-2">명시적인 FROM이 있는 Dockerfile을 고정 커밋에서 가져옵니다. 서버가 FROM과 빌드 컨텍스트를 검증한 뒤 같은 작업 기록에 추가합니다.</p>
            {#if importForm.ref && !pinnedCommitValid}
              <p class="text-xs text-red-300">브랜치나 태그 대신 40자리 commit SHA를 입력하세요.</p>
            {/if}
          {/if}

          <!-- 공통 레이어 빌드 옵션 -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="dockerfile-layer-prefix">Layer prefix *</label>
              <input
                id="dockerfile-layer-prefix"
                type="text"
                placeholder="예: demo"
                bind:value={importForm.layer_prefix}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
              />
            </div>
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="dockerfile-profile-name">Profile name (선택)</label>
              <input
                id="dockerfile-profile-name"
                type="text"
                placeholder="비우면 prefix 사용"
                bind:value={importForm.profile_name}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
              />
            </div>
          </div>
          <ToggleGroup value={dockerfileTarget} options={dockerfileTargetOptions} onchange={(value) => dockerfileTarget = value as DockerfileExecutionTarget} size="sm" fullWidth ariaLabel="Dockerfile 실행 목표" />
          {#if dockerfileTarget === 'instance'}
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 p-3 bg-surface-base border border-line-2 rounded-lg" aria-label="Dockerfile 소비 VM 설정">
              <p class="md:col-span-2 text-xs text-ink-2">베이스 이미지와 프로필은 Dockerfile의 FROM과 설정된 이름에서 자동으로 이어받습니다.</p>
              <div><label class="block text-xs text-ink-2 mb-1" for="dockerfile-consumer-flavor">소비 VM Flavor ID *</label><input id="dockerfile-consumer-flavor" type="text" bind:value={dockerfileConsumer.flavor_id} class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0" /></div>
              <div><label class="block text-xs text-ink-2 mb-1" for="dockerfile-consumer-server">소비 VM 서버 이름 (선택)</label><input id="dockerfile-consumer-server" type="text" bind:value={dockerfileConsumer.server_name} class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0" /></div>
              <div><label class="block text-xs text-ink-2 mb-1" for="dockerfile-consumer-network">소비 VM Network ID (선택)</label><input id="dockerfile-consumer-network" type="text" bind:value={dockerfileConsumer.network_id} class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0" /></div>
              <div><label class="block text-xs text-ink-2 mb-1" for="dockerfile-consumer-keypair">소비 VM 접속 키페어 (SSH 공개키가 없을 때 필수)</label><select id="dockerfile-consumer-keypair" bind:value={dockerfileConsumer.key_name} class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0"><option value="">선택 안 함</option>{#each keypairs as kp}<option value={kp.name}>{kp.name}</option>{/each}</select></div>
              <div><label class="block text-xs text-ink-2 mb-1" for="dockerfile-consumer-user">소비 VM SSH 사용자 (선택)</label><input id="dockerfile-consumer-user" type="text" bind:value={dockerfileConsumer.ssh_username} class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0" /></div>
              <div><label class="block text-xs text-ink-2 mb-1" for="dockerfile-consumer-pubkey">소비 VM SSH 공개키 (키페어가 없을 때 필수)</label><textarea id="dockerfile-consumer-pubkey" rows="2" bind:value={dockerfileConsumer.ssh_public_key} class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 font-mono"></textarea></div>
            </div>
          {/if}
          {#if dockerfileMode !== 'github'}
            <DockerfileLintPanel lint={dockerfileLint} loading={lintLoading} requestError={lintError} />
          {/if}

          <!-- 빌드 계획 미리보기 결과 표시 -->
          {#if planError}
            <Alert tone="danger">
              <span class="font-semibold">계획 오류:</span> {planError}
            </Alert>
          {/if}

          {#if dockerfilePlan}
            <div class="p-3 bg-surface-base border border-line-2 rounded-lg space-y-2 text-xs">
              <div class="flex items-center justify-between">
                <span class="font-semibold text-ink-0">빌드 계획 (미리보기)</span>
                <span class="text-ink-2 font-mono">{dockerfilePlan.ubuntu_base}</span>
              </div>
              <div class="text-ink-2 font-mono truncate" title={dockerfilePlan.dockerfile_digest}>
                Digest: {dockerfilePlan.dockerfile_digest.slice(0, 20)}…
              </div>
              <p class="text-state-success">캐시 재사용 artifact: {dockerfilePlan.cached_artifact_ids.map(id => `#${id}`).join(', ') || '없음'}</p>
              <div class="space-y-1 max-h-36 overflow-y-auto">
                {#each dockerfilePlan.steps as step, idx}
                  <div class="flex items-center justify-between gap-2 p-1.5 rounded bg-surface-sunken border border-line-2">
                    <div class="flex items-center gap-1.5 min-w-0">
                      <span class="font-semibold text-ink-1">#{idx + 1}</span>
                      <span class="px-1.5 py-0.5 rounded font-mono text-xs bg-surface-selected text-ink-0">{step.instruction}</span>
                      <span class="font-mono text-ink-2 truncate max-w-xs">{step.args}</span>
                    </div>
                      <span class="text-xs text-warm-text font-mono whitespace-nowrap">신규 빌드</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <!-- 액션 버튼 -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
            {#if dockerfileMode !== 'github'}
              <Button
                variant="secondary"
                size="sm"
                onclick={previewDockerfilePlan}
                disabled={planLoading || lintLoading || dockerfileFetching || !dockerfileText.trim() || !importForm.layer_prefix.trim() || (dockerfileLint !== null && !dockerfileLint.valid)}
                class="w-full"
              >
                {planLoading ? '계획 계산 중...' : '빌드 계획 미리보기'}
              </Button>
              <Button
                variant="primary"
                size="sm"
                onclick={submitInlineDockerfileBuild}
                disabled={importSubmitting || lintLoading || dockerfileFetching || !dockerfileConsumerReady || !dockerfileText.trim() || !importForm.layer_prefix.trim() || (dockerfileLint !== null && !dockerfileLint.valid)}
                class="w-full"
              >
                {importSubmitting ? '빌드 시작 중...' : 'Dockerfile 빌드 시작'}
              </Button>
            {:else}
              <Button
                variant="accent"
                size="sm"
                onclick={submitDockerfileImport}
                disabled={importSubmitting || !dockerfileConsumerReady || !pinnedCommitValid || !importForm.github_url.trim() || !importForm.layer_prefix.trim()}
                class="w-full sm:col-span-2"
              >
                {importSubmitting ? 'Import 시작 중...' : 'GitHub Dockerfile import 시작'}
              </Button>
            {/if}
          </div>

          <!-- importJobs 테이블 -->
          <h3 class="text-sm font-semibold text-ink-0">Dockerfile 작업 기록</h3>
          {#if importLoadError}<Alert tone="danger">{importLoadError}</Alert>{/if}
          {#if selectedImport}
            <section aria-label="선택한 Dockerfile 작업" class="p-3 border border-line-2 rounded-lg space-y-2 text-xs">
              <p class="font-mono">#{selectedImport.id} · {selectedImport.profile_name} · {selectedImport.source_type || 'github'}</p>
              <StatusChip status={selectedImport.status} />
              <p>{selectedImport.progress_step || selectedImport.status} · {selectedImport.progress_pct}%</p>
              <progress class="w-full" aria-label="Dockerfile 작업 진행률" max="100" value={selectedImport.progress_pct}></progress>
              {#if selectedImport.error_message}<Alert tone="danger">{selectedImport.error_message}</Alert>{/if}
              <p>Base: {selectedImport.base_image_name || selectedImport.base_image_id || selectedImport.ubuntu_base}</p>
              {#if selectedImport.github_url}<p class="break-all">{selectedImport.github_url} · {selectedImport.commit_sha} · {selectedImport.dockerfile_path}</p>{/if}
              {#if selectedImport.dockerfile_digest}<p class="break-all">Digest: {selectedImport.dockerfile_digest}</p>{/if}
              <p>Artifact: {selectedImport.artifact_ids?.map(id => `#${id}`).join(', ') || '—'}</p>
              <p>Build: {selectedImport.build_ids?.map(id => `#${id}`).join(', ') || '—'}</p>
              {#if selectedImport.consume_id || selectedImport.consumer_status || selectedImport.consumer_spec}
                <p>소비 VM: {selectedImport.consume_id ? `#${selectedImport.consume_id}` : '예약됨'} · {selectedImport.consumer_status || '대기'} {#if selectedImport.consumer_spec}({selectedImport.consumer_spec.server_name || '자동 이름'} · {selectedImport.consumer_spec.flavor_id}){/if}</p>
                {#if selectedImport.consume_id}
                  <button type="button" class="underline" onclick={() => { selectedConsumeId = selectedImport.consume_id!; consumeDetailOpen = true; }}>소비 VM #{selectedImport.consume_id} 상세</button>
                {/if}
              {/if}
              {#if selectedImport.status === 'complete' && selectedImport.dockerfile_digest && selectedImport.artifact_ids?.length}
                <Button variant="secondary" size="sm" onclick={() => { historyConsumeTargetId = historyConsumeTargetId === selectedImport.id ? null : selectedImport.id; historyConsumeError = ''; }} disabled={historyConsumeSubmitting}>
                  {historyConsumeTargetId === selectedImport.id ? 'VM 생성 설정 닫기' : '이 작업의 artifact로 VM 생성'}
                </Button>
                {#if historyConsumeTargetId === selectedImport.id}
                  <div class="grid grid-cols-1 md:grid-cols-2 gap-3 p-3 bg-surface-base border border-line-2 rounded-lg" aria-label="작업 artifact 소비 VM 설정">
                    <p class="md:col-span-2 text-ink-2">작업 #{selectedImport.id}의 봉인된 artifact #{selectedImport.artifact_ids.join(', #')}을 사용합니다. 현재 프로필 이름으로 재조회하지 않습니다.</p>
                    <div><label class="block text-ink-2 mb-1" for="history-consumer-flavor">Flavor ID *</label><input id="history-consumer-flavor" type="text" bind:value={historyConsumer.flavor_id} class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0" /></div>
                    <div><label class="block text-ink-2 mb-1" for="history-consumer-server">서버 이름 (선택)</label><input id="history-consumer-server" type="text" bind:value={historyConsumer.server_name} class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0" /></div>
                    <div><label class="block text-ink-2 mb-1" for="history-consumer-network">Network ID (선택)</label><input id="history-consumer-network" type="text" bind:value={historyConsumer.network_id} class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0" /></div>
                    <div><label class="block text-ink-2 mb-1" for="history-consumer-keypair">접속 키페어 (SSH 공개키가 없을 때 필수)</label><select id="history-consumer-keypair" bind:value={historyConsumer.key_name} class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0"><option value="">선택 안 함</option>{#each keypairs as kp}<option value={kp.name}>{kp.name}</option>{/each}</select></div>
                    <div><label class="block text-ink-2 mb-1" for="history-consumer-user">SSH 사용자 (선택)</label><input id="history-consumer-user" type="text" bind:value={historyConsumer.ssh_username} class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0" /></div>
                    <div><label class="block text-ink-2 mb-1" for="history-consumer-pubkey">SSH 공개키 (키페어가 없을 때 필수)</label><textarea id="history-consumer-pubkey" rows="2" bind:value={historyConsumer.ssh_public_key} class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 font-mono"></textarea></div>
                    {#if historyConsumeError}<div class="md:col-span-2"><Alert tone="danger">{historyConsumeError}</Alert></div>{/if}
                    <div class="md:col-span-2"><Button variant="primary" size="sm" onclick={() => consumeCompletedImport(selectedImport)} disabled={!historyConsumerReady || historyConsumeSubmitting}>{historyConsumeSubmitting ? 'VM 생성 중...' : '선택한 작업으로 VM 생성'}</Button></div>
                  </div>
                {/if}
              {/if}
              <p>생성: {fmtDate(selectedImport.created_at)} · 완료: {fmtDate(selectedImport.completed_at)}</p>
              {#each selectedImport.planned_layers ?? [] as step}
                <p class="font-mono">L{step.line} · {step.name} · {step.instruction}</p>
              {/each}
            </section>
          {/if}
          {#if importJobs.length > 0}
            <div class="border border-line-2 rounded-lg overflow-x-auto mt-3">
              <table class="min-w-full text-xs">
                <thead class="bg-surface-base text-ink-2">
                  <tr>
                    <th class="px-3 py-2 text-left">ID</th>
                    <th class="px-3 py-2 text-left">Profile</th>
                    <th class="px-3 py-2 text-left">Base image</th>
                    <th class="px-3 py-2 text-left">Status</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-line">
                  {#each importJobs as job}
                    <tr>
                      <td class="px-3 py-2 text-ink-2"><button type="button" class="underline" aria-label={`작업 #${job.id} 상세`} onclick={() => selectedImportId = job.id}>#{job.id}</button></td>
                      <td class="px-3 py-2 font-mono">{job.profile_name}</td>
                      <td class="px-3 py-2 text-ink-2">{job.base_image_name || shortId(job.base_image_id)}</td>
                      <td class="px-3 py-2"><StatusChip status={job.status} /><p class="mt-1">{job.progress_step || job.status} · {job.progress_pct}%</p>{#if job.consumer_status || job.consume_id}<p>VM {job.consume_id ? `#${job.consume_id}` : ''} {job.consumer_status || ''}</p>{/if}{#if job.error_message}<p class="text-red-300">{job.error_message}</p>{/if}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </div>
      </section>

    </div>

    <!-- ---------------------------------------------------------------------- -->
    <!-- 프로필 구성 카드                                                        -->
    <!-- ---------------------------------------------------------------------- -->
    <div class="mb-8">
      <section class="bg-surface-sunken border border-line-2 rounded-xl p-5" data-tour="admin-library-profile">
        <h2 class="text-sm font-semibold text-ink-0 mb-1">프로필 기록</h2>
        <p class="text-xs text-ink-2 mb-4">
          Dockerfile 빌드로 생성된 프로필과 기존 프로필의 계보·공개 상태를 조회하고 관리합니다. 새 VM은 상단 Dockerfile 빌드에서 생성합니다.
        </p>
        {#if profileDeleteError}
          <div class="mb-3 p-2 bg-red-900/40 border border-red-700 rounded text-red-300 text-xs">{profileDeleteError}</div>
        {/if}
        {#if profileMessage}
          <div class="mb-3 p-2 bg-green-900/40 border border-green-700 rounded text-green-300 text-xs">{profileMessage}</div>
        {/if}
        {#if selectedHistoricalProfile}
          <div class="mb-3 p-3 border border-line-2 rounded text-xs" aria-label="선택한 프로필">
            <p class="font-mono">#{selectedHistoricalProfile.id} {selectedHistoricalProfile.name}</p>
            <p>{selectedHistoricalProfile.layers.join(' → ')}</p>
            <p>생성: {fmtDate(selectedHistoricalProfile.created_at)} · 수정: {fmtDate(selectedHistoricalProfile.updated_at)}</p>
          </div>
        {/if}
            {#if profiles.length > 0}
              <div class="pt-3 border-t border-line-2">
                <p class="text-xs text-ink-2 mb-2">저장된 프로필</p>
                <div class="overflow-x-auto border border-line-2 rounded-lg">
                  <table class="w-full text-xs">
                    <thead>
                      <tr class="text-ink-2 bg-surface-base/80">
                        <th class="text-left px-3 py-2">이름</th>
                        <th class="text-left px-3 py-2">레이어 체인</th>
                        <th class="text-left px-3 py-2">활성 consume</th>
                        <th class="text-left px-3 py-2">공개</th>
                        <th class="px-3 py-2"></th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-line/50">
                      {#each profiles as profile (profile.id)}
                        {@const blockers = blockingConsumesForProfile(profile.name)}
                        <tr>
                          <td class="px-3 py-2 font-mono text-ink-1">{profile.name}</td>
                          <td class="px-3 py-2 text-ink-2">{profile.layers.join(' → ')}</td>
                          <td class="px-3 py-2 text-ink-2">{blockers.length}</td>
                          <td class="px-3 py-2">
                            <span class="{profile.is_published ? 'text-warm-text' : 'text-ink-2'}">{profile.is_published ? '공개' : '비공개'}</span>
                          </td>
                          <td class="px-3 py-2">
                            <div class="flex justify-end gap-2">
                              <button
                                onclick={() => selectedProfileId = profile.id}
                                class="px-2 py-1 rounded border border-line-2 text-ink-2 hover:border-gray-400 transition-colors"
                              >
                                상세
                              </button>
                              <button
                                type="button"
                                onclick={() => setProfilePublication(profile, !profile.is_published)}
                                disabled={publicationUpdating === `profile:${profile.name}`}
                                class="px-2 py-1 rounded border border-action-warm text-warm-text hover:border-action-warm disabled:border-line-2 disabled:text-ink-3 disabled:cursor-not-allowed transition-colors"
                              >
                                {publicationUpdating === `profile:${profile.name}` ? '변경 중...' : (profile.is_published ? '비공개' : '공개')}
                              </button>
                              <button
                                type="button"
                                onclick={() => deleteProfile(profile)}
                                disabled={blockers.length > 0 || profileDeletingName === profile.name}
                                title={blockers.length > 0 ? '사용 중인 소비 VM을 삭제하거나 deleted 상태로 동기화한 뒤 삭제할 수 있습니다' : '프로필 삭제'}
                                class="px-2 py-1 rounded border border-red-800 text-red-300 hover:border-red-500 disabled:border-line-2 disabled:text-ink-3 disabled:cursor-not-allowed transition-colors"
                              >
                                {profileDeletingName === profile.name ? '삭제 중...' : '삭제'}
                              </button>
                            </div>
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              </div>
            {/if}
      </section>
    </div>

    <!-- ---------------------------------------------------------------------- -->
    <!-- 아티팩트 현황 / 삭제                                                    -->
    <!-- ---------------------------------------------------------------------- -->
    <div class="mb-6" data-tour="admin-library-artifacts">
      <h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-2">아티팩트 현황</h3>
      {#if artifacts.length === 0}
        <div class="bg-surface-sunken border border-line-2 rounded-xl p-6 text-center text-ink-2 text-sm">
          생성된 artifact가 없습니다
        </div>
      {:else}
        <div class="bg-surface-sunken border border-line-2 rounded-xl overflow-hidden">
          <div class="max-h-80 overflow-y-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-xs text-ink-2 uppercase tracking-wide sticky top-0 z-10 bg-surface-sunken [box-shadow:inset_0_-1px_0_#374151]">
                  <th class="text-left px-4 py-2.5">Artifact</th>
                  <th class="text-left px-4 py-2.5 hidden md:table-cell">상속 체인</th>
                  <th class="text-left px-4 py-2.5 hidden lg:table-cell">요청 패키지</th>
                  <th class="text-left px-4 py-2.5 hidden xl:table-cell">삭제 상태</th>
                  <th class="px-4 py-2.5"></th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line/50">
                {#each artifacts as a (a.id)}
                  <tr class="hover:bg-surface-selected/30 transition-colors">
                    <td class="px-4 py-2.5">
                      <div class="font-mono text-ink-0">#{a.id} {a.name}</div>
                      <div class="mt-1 flex items-center gap-1.5 text-xs text-ink-2">
                        <span class="px-1.5 py-0.5 rounded {a.kind === 'uv' ? 'bg-surface-selected/60 text-warm-text' : 'bg-indigo-900/60 text-indigo-300'}">{a.kind}</span>
                        {#if a.python_version}<span>py{a.python_version}</span>{/if}
                        <span>{a.is_sealed ? 'sealed' : 'unsealed'}</span>
                      </div>
                      <div class="mt-0.5 text-xs text-ink-2 truncate" title={ubuntuBaseLabel(a)}>Ubuntu: {ubuntuBaseLabel(a)}</div>
                    </td>
                    <td class="px-4 py-2.5 text-ink-2 text-xs font-mono hidden md:table-cell max-w-md truncate" title={artifactChainLabel(a)}>
                      {artifactChainLabel(a)}
                    </td>
                    <td class="px-4 py-2.5 text-ink-2 text-xs hidden lg:table-cell max-w-xs truncate" title={packageLabel(a)}>
                      {packageLabel(a)}
                    </td>
                    <td class="px-4 py-2.5 text-xs hidden xl:table-cell">
                      {#if a.can_delete}
                        <span class="text-green-400">삭제 가능</span>
                      {:else}
                        <span class="text-yellow-400">차단 {a.delete_blockers.length}건</span>
                      {/if}
                    </td>
                    <td class="px-4 py-2.5 text-right">
                      <button
                        type="button"
                        onclick={() => setArtifactPublication(a, !a.is_published)}
                        disabled={!a.is_sealed || publicationUpdating === `artifact:${a.id}`}
                        class="mr-3 text-xs {a.is_published ? 'text-warm-text hover:text-warm-text-hover' : 'text-ink-2 hover:text-ink-0'} disabled:text-ink-3 disabled:cursor-not-allowed transition-colors"
                        title={!a.is_sealed ? '봉인된 artifact만 공개할 수 있습니다' : (a.is_published ? '사용자 VM 마법사에서 숨기기' : '사용자 VM 마법사에 공개')}
                      >{publicationUpdating === `artifact:${a.id}` ? '변경 중...' : (a.is_published ? '공개 중' : '비공개')}</button>
                      <button
                        type="button"
                        onclick={() => openDeletePreview(a)}
                        class="text-xs {a.can_delete ? 'text-red-400 hover:text-red-300' : 'text-yellow-400 hover:text-yellow-300'} transition-colors"
                      >삭제 검토</button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      {/if}
    </div>

    <!-- ---------------------------------------------------------------------- -->
    <!-- 빌드 현황 테이블                                                        -->
    <!-- ---------------------------------------------------------------------- -->
    <div class="mb-6" data-tour="admin-library-builds">
      <h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-2">
        빌드 현황
        {#if activeBuilds.length > 0}
          <span class="ml-2 text-warm-text normal-case">(10초마다 자동 갱신)</span>
        {/if}
      </h3>
      {#if builds.length === 0}
        <div class="bg-surface-sunken border border-line-2 rounded-xl p-6 text-center text-ink-2 text-sm">
          빌드 기록이 없습니다
        </div>
      {:else}
        <div class="bg-surface-sunken border border-line-2 rounded-xl overflow-hidden">
          <div class="max-h-72 overflow-y-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-xs text-ink-2 uppercase tracking-wide sticky top-0 z-10 bg-surface-sunken [box-shadow:inset_0_-1px_0_#374151]">
                  <th class="text-left px-4 py-2.5">레이어 이름</th>
                  <th class="text-left px-4 py-2.5 hidden sm:table-cell">Kind / Python</th>
                  <th class="text-left px-4 py-2.5">상태</th>
                  <th class="text-left px-4 py-2.5 hidden md:table-cell">단계</th>
                  <th class="text-left px-4 py-2.5 w-36 hidden lg:table-cell">진행률</th>
                  <th class="text-left px-4 py-2.5 hidden xl:table-cell">VM</th>
                  <th class="text-left px-4 py-2.5 hidden lg:table-cell">시작</th>
                  <th class="px-4 py-2.5"></th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line/50">
                {#each builds as build (build.id)}
                  {@const isDone = TERMINAL.has(build.status)}
                  <tr
                    class="hover:bg-surface-selected/30 transition-colors cursor-pointer {isDone ? 'opacity-50' : ''}"
                    onclick={() => openBuildDetail(build)}
                  >
                    <td class="px-4 py-2.5 font-medium text-ink-0 max-w-28 truncate">
                      <div class="truncate">{build.layer_name}</div>
                      {#if buildPackageLabel(build) !== '—'}
                        <div class="mt-0.5 text-xs text-ink-2 truncate" title={buildPackageLabel(build)}>{buildPackageLabel(build)}</div>
                      {/if}
                    </td>
                    <td class="px-4 py-2.5 text-ink-2 text-xs font-mono hidden sm:table-cell">
                      <span class="text-xs px-1.5 py-0.5 rounded mr-1 {build.kind === 'uv' ? 'bg-surface-selected/60 text-warm-text' : 'bg-indigo-900/60 text-indigo-300'}">{build.kind ?? 'python'}</span>
                      {build.python_version ?? ''}
                      <div class="mt-0.5 text-xs text-ink-2 truncate" title={ubuntuBaseLabel(build)}>Ubuntu: {ubuntuBaseLabel(build)}</div>
                    </td>
                    <td class="px-4 py-2.5">
                      <StatusChip status={build.status} />
                    </td>
                    <td class="px-4 py-2.5 text-ink-2 text-xs hidden md:table-cell max-w-40 truncate">
                      {build.progress_step || '—'}
                    </td>
                    <td class="px-4 py-2.5 hidden lg:table-cell">
                      <div class="flex items-center gap-2">
                        <div class="flex-1 h-1 bg-surface-selected rounded-full overflow-hidden">
                          <div
                            class="h-full rounded-full {build.status === 'complete' ? 'bg-green-500' : build.status === 'error' ? 'bg-red-500' : 'bg-action-warm'}"
                            style="width:{build.progress_pct}%"
                          ></div>
                        </div>
                        <span class="text-xs text-ink-2 w-8 text-right">{build.progress_pct}%</span>
                      </div>
                    </td>
                    <td class="px-4 py-2.5 text-ink-2 text-xs font-mono hidden xl:table-cell">
                      {build.server_id ? build.server_id.slice(0, 8) + '…' : '—'}
                    </td>
                    <td class="px-4 py-2.5 text-ink-2 text-xs hidden lg:table-cell">
                      {fmtRelative(build.started_at)}
                    </td>
                    <td class="px-4 py-2.5 text-right">
                      <button
                        onclick={(e) => { e.stopPropagation(); openBuildDetail(build); }}
                        class="text-xs text-warm-text hover:text-warm-text-hover transition-colors"
                      >상세</button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      {/if}
    </div>

    <!-- ---------------------------------------------------------------------- -->
    <!-- 소비 인스턴스 테이블                                                    -->
    <!-- ---------------------------------------------------------------------- -->
    <div data-tour="admin-library-consumes">
      <h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-2">소비 인스턴스</h3>
      {#if consumes.length === 0}
        <div class="bg-surface-sunken border border-line-2 rounded-xl p-6 text-center text-ink-2 text-sm">
          생성된 소비 인스턴스가 없습니다
        </div>
      {:else}
        <div class="bg-surface-sunken border border-line-2 rounded-xl overflow-hidden">
          <div class="max-h-72 overflow-y-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-xs text-ink-2 uppercase tracking-wide sticky top-0 z-10 bg-surface-sunken [box-shadow:inset_0_-1px_0_#374151]">
                  <th class="text-left px-4 py-2.5">서버 이름</th>
                  <th class="text-left px-4 py-2.5 hidden sm:table-cell">프로필</th>
                  <th class="text-left px-4 py-2.5">상태</th>
                  <th class="text-left px-4 py-2.5 hidden xl:table-cell">서버 ID</th>
                  <th class="text-left px-4 py-2.5 hidden lg:table-cell">생성</th>
                  <th class="px-4 py-2.5"></th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line/50">
                {#each consumes as c (c.id)}
                  <tr
                    class="hover:bg-surface-selected/30 transition-colors cursor-pointer"
                    onclick={() => openConsumeDetail(c)}
                  >
                    <td class="px-4 py-2.5 font-medium text-ink-0 max-w-28 truncate">{c.server_name ?? '—'}</td>
                    <td class="px-4 py-2.5 text-ink-2 text-xs hidden sm:table-cell">{c.profile_name}</td>
                    <td class="px-4 py-2.5">
                      <StatusChip status={c.status} />
                    </td>
                    <td class="px-4 py-2.5 text-ink-2 text-xs font-mono hidden xl:table-cell">
                      {c.server_id ? c.server_id.slice(0, 8) + '…' : '—'}
                    </td>
                    <td class="px-4 py-2.5 text-ink-2 text-xs hidden lg:table-cell">
                      {fmtRelative(c.created_at)}
                    </td>
                    <td class="px-4 py-2.5 text-right">
                      <button
                        onclick={(e) => { e.stopPropagation(); openConsumeDetail(c); }}
                        class="text-xs text-purple-400 hover:text-purple-300 transition-colors"
                      >상세</button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>

<!-- -------------------------------------------------------------------------- -->
<!-- 빌드 상세 모달                                                              -->
<!-- -------------------------------------------------------------------------- -->
<Modal bind:open={detailOpen} ariaLabel="레이어 빌드 상세">
  {#if detailOpen}
    <div class="bg-surface-base rounded-xl border border-line-2 w-full max-w-2xl mx-auto p-6 space-y-5">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-xs text-ink-2 mb-1">레이어 빌드 상세</p>
          <h2 class="text-base font-semibold text-ink-0">{buildDetail?.layer_name ?? '—'}</h2>
          {#if buildDetail}
            <p class="text-xs text-ink-2 mt-0.5">Ubuntu: {ubuntuBaseLabel(buildDetail)}</p>
          {/if}
          <p class="text-xs text-ink-2 mt-0.5">Kind: {buildDetail?.kind ?? '—'}{buildDetail?.python_version ? ` · Python ${buildDetail.python_version}` : ''}</p>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          {#if buildDetail?.status}
            <StatusChip status={buildDetail.status} />
          {/if}
          <button
            onclick={() => (detailOpen = false)}
            class="text-ink-2 hover:text-ink-0 transition-colors ml-2"
            aria-label="닫기"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {#if detailLoading && !buildDetail}
        <div class="space-y-2">
          {#each [1, 2, 3] as _}
            <div class="h-8 bg-surface-sunken rounded animate-pulse"></div>
          {/each}
        </div>
      {:else if buildDetail}
        <!-- 진행률 바 -->
        <div>
          <div class="flex justify-between text-xs text-ink-2 mb-1">
            <span>{buildDetail.progress_step || '대기 중'}</span>
            <span>{buildDetail.progress_pct}%</span>
          </div>
          <div class="h-1.5 bg-surface-selected rounded-full overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-500 {buildDetail.status === 'complete' ? 'bg-green-500' : buildDetail.status === 'error' || buildDetail.status === 'cancelled' ? 'bg-red-500' : 'bg-action-warm'}"
              style="width: {buildDetail.progress_pct}%"
            ></div>
          </div>
        </div>

        <!-- 정보 그리드 -->
        <div class="grid grid-cols-2 gap-3 text-xs">
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-0.5">VM 인스턴스</p>
            <p class="text-ink-0 font-mono truncate">{buildDetail.server_id ? buildDetail.server_id.slice(0, 18) + '…' : '—'}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-0.5">VM 상태</p>
            {#if buildDetail.vm_status}
              <StatusChip status={buildDetail.vm_status.toLowerCase()} />
            {:else}
              <p class="text-ink-2">—</p>
            {/if}
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-0.5">VM IP</p>
            <p class="text-ink-0 font-mono">{buildDetail.vm_ip ?? '—'}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-0.5">경과 시간</p>
            <p class="text-ink-0">{elapsed(buildDetail.started_at)}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-0.5">시작 시각</p>
            <p class="text-ink-0">{fmtDate(buildDetail.started_at)}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-0.5">완료 시각</p>
            <p class="text-ink-0">{fmtDate(buildDetail.completed_at)}</p>
          </div>
          {#if buildDetail.share_id}
            <div class="col-span-2 bg-surface-sunken/60 rounded-lg px-3 py-2.5">
              <p class="text-ink-2 mb-0.5">NFS Share ID</p>
              <p class="text-ink-0 font-mono text-xs truncate">{buildDetail.share_id}</p>
            </div>
          {/if}
        </div>

        {#if buildDetail.error_message}
          <div class="bg-red-900/30 border border-red-700/50 rounded-lg px-3 py-2.5">
            <p class="text-xs text-red-400 font-medium mb-1">오류</p>
            <p class="text-xs text-red-300 font-mono whitespace-pre-wrap break-all">{buildDetail.error_message}</p>
          </div>
        {/if}

        <!-- 콘솔 로그 -->
        <div>
          <div class="flex items-center justify-between mb-1.5">
            <p class="text-xs text-ink-2">
              {#if buildDetail.live_console}
                콘솔 로그 {detailIsActive ? '(10초마다 자동 갱신)' : ''}
              {:else if buildDetail.console_log_excerpt}
                마지막 저장 로그
              {:else}
                콘솔 로그
              {/if}
            </p>
            {#if detailIsActive}
              <button
                onclick={loadBuildDetail}
                class="text-xs text-warm-text hover:text-warm-text-hover transition-colors"
              >새로고침</button>
            {/if}
          </div>
          {#if buildDetail.live_console || buildDetail.console_log_excerpt}
            <pre class="bg-surface-canvas text-xs text-ink-2 font-mono whitespace-pre-wrap break-all overflow-auto max-h-56 rounded-lg p-3 border border-line">{buildDetail.live_console || buildDetail.console_log_excerpt}</pre>
          {:else}
            <div class="bg-surface-canvas rounded-lg p-3 border border-line text-xs text-ink-2 font-mono">
              로그 없음
            </div>
          {/if}
        </div>

        <!-- 하단 액션 -->
        <div class="flex items-center justify-between pt-1 border-t border-line">
          {#if detailCancelError}
            <p class="text-xs text-red-400">{detailCancelError}</p>
          {:else}
            <div></div>
          {/if}
          <div class="flex gap-2">
            {#if detailIsActive}
              <button
                onclick={cancelBuild}
                disabled={detailCancelling}
                class="px-3 py-1.5 text-xs text-red-400 border border-red-700/50 hover:bg-red-900/30 disabled:opacity-50 rounded-lg transition-colors"
              >
                {detailCancelling ? '취소 중...' : '빌드 취소'}
              </button>
            {/if}
            <button
              onclick={() => (detailOpen = false)}
              class="px-3 py-1.5 text-xs text-ink-2 border border-line-2 hover:bg-surface-sunken rounded-lg transition-colors"
            >닫기</button>
          </div>
        </div>
      {/if}
    </div>
  {/if}
</Modal>

<!-- -------------------------------------------------------------------------- -->
<!-- 소비 상세 모달                                                              -->
<!-- -------------------------------------------------------------------------- -->
<Modal bind:open={consumeDetailOpen} ariaLabel="레이어 소비 상세">
  {#if consumeDetailOpen}
    <div class="bg-surface-base rounded-xl border border-line-2 w-full max-w-xl mx-auto p-6 space-y-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-xs text-ink-2 mb-1">소비 인스턴스 상세</p>
          <h2 class="text-base font-semibold text-ink-0">{consumeDetail?.server_name ?? '—'}</h2>
          <p class="text-xs text-ink-2 mt-0.5">프로필: {consumeDetail?.profile_name ?? '—'}</p>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          {#if consumeDetail?.status}
            <StatusChip status={consumeDetail.status} />
          {/if}
          <button
            onclick={() => (consumeDetailOpen = false)}
            class="text-ink-2 hover:text-ink-0 transition-colors ml-2"
            aria-label="닫기"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {#if consumeDetailLoading && !consumeDetail}
        <div class="space-y-2">
          {#each [1, 2, 3] as _}
            <div class="h-8 bg-surface-sunken rounded animate-pulse"></div>
          {/each}
        </div>
      {:else if consumeDetail}
        <div class="grid grid-cols-2 gap-3 text-xs">
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-0.5">서버 ID</p>
            <p class="text-ink-0 font-mono truncate">{consumeDetail.server_id ? consumeDetail.server_id.slice(0, 18) + '…' : '—'}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-0.5">VM 상태</p>
            {#if consumeDetail.vm_status}
              <StatusChip status={consumeDetail.vm_status.toLowerCase()} />
            {:else}
              <p class="text-ink-2">—</p>
            {/if}
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-0.5">VM IP</p>
            <p class="text-ink-0 font-mono">{consumeDetail.vm_ip ?? '—'}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-0.5">생성 시각</p>
            <p class="text-ink-0">{fmtDate(consumeDetail.created_at)}</p>
          </div>
          {#if consumeDetail.share_id}
            <div class="col-span-2 bg-surface-sunken/60 rounded-lg px-3 py-2.5">
              <p class="text-ink-2 mb-0.5">NFS Share ID (RO)</p>
              <p class="text-ink-0 font-mono text-xs truncate">{consumeDetail.share_id}</p>
            </div>
          {/if}
        </div>

        {#if consumeDetail.error_message}
          <div class="bg-red-900/30 border border-red-700/50 rounded-lg px-3 py-2.5">
            <p class="text-xs text-red-400 font-medium mb-1">오류</p>
            <p class="text-xs text-red-300 font-mono whitespace-pre-wrap break-all">{consumeDetail.error_message}</p>
          </div>
        {/if}

        <div class="flex justify-end pt-1 border-t border-line">
          <button
            onclick={() => (consumeDetailOpen = false)}
            class="px-3 py-1.5 text-xs text-ink-2 border border-line-2 hover:bg-surface-sunken rounded-lg transition-colors"
          >닫기</button>
        </div>
      {/if}
    </div>
  {/if}
</Modal>

<!-- -------------------------------------------------------------------------- -->
<!-- 아티팩트 삭제 미리보기 모달                                                  -->
<!-- -------------------------------------------------------------------------- -->
<Modal bind:open={deleteModalOpen} ariaLabel="레이어 삭제">
  {#if deleteModalOpen}
    <div class="bg-surface-base rounded-xl border border-line-2 w-full max-w-2xl mx-auto p-6 space-y-5">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-xs text-ink-2 mb-1">Artifact 삭제 미리보기</p>
          <h2 class="text-base font-semibold text-ink-0">
            {deletePreview ? `#${deletePreview.artifact.id} ${deletePreview.artifact.name}` : '조회 중'}
          </h2>
          <p class="text-xs text-ink-2 mt-0.5">삭제는 leaf artifact만 허용됩니다. 이름 기반 프로필 참조는 보수적으로 차단합니다.</p>
        </div>
        <button
          onclick={() => (deleteModalOpen = false)}
          class="text-ink-2 hover:text-ink-0 transition-colors"
          aria-label="닫기"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {#if deleteLoading}
        <div class="space-y-2">
          {#each [1, 2, 3] as _}
            <div class="h-8 bg-surface-sunken rounded animate-pulse"></div>
          {/each}
        </div>
      {:else if deletePreview}
        <div class="space-y-3 text-xs">
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-1">상속 체인</p>
            <p class="text-ink-0 font-mono break-all">{deletePreview.lineage.map(a => `${a.name}#${a.id}`).join(' → ')}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-1">Ubuntu base</p>
            <p class="text-ink-0 break-all">{ubuntuBaseLabel(deletePreview.artifact)}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-2 mb-1">요청 패키지</p>
            <p class="text-ink-0 break-all">{packageLabel(deletePreview.artifact)}</p>
          </div>

          {#if deletePreview.can_delete}
            <div class="bg-green-900/20 border border-green-700/40 rounded-lg px-3 py-2.5 text-green-300">
              차단 사유 없음. Manila share access rule 회수 후 share와 DB row를 삭제합니다.
            </div>
          {:else}
            <div class="bg-yellow-900/20 border border-yellow-700/40 rounded-lg px-3 py-2.5">
              <p class="text-yellow-300 font-medium mb-2">삭제 차단 사유</p>
              <div class="space-y-2">
                {#each deletePreview.delete_blockers as blocker}
                  <div class="rounded border border-yellow-700/30 bg-surface-canvas/40 p-2">
                    <p class="text-yellow-200">{blocker.message}</p>
                    <p class="mt-1 text-xs text-ink-2 font-mono break-all">{JSON.stringify(blocker.items)}</p>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <div class="bg-surface-canvas/60 border border-line rounded-lg px-3 py-2.5 text-ink-2">
            현재 프로필은 artifact ID가 아니라 layer name 목록을 저장합니다. 같은 이름을 포함한 프로필이나 그 프로필을 쓰는 활성 consume이 있으면 삭제할 수 없습니다.
          </div>
        </div>
      {/if}

      {#if deleteError}
        <div class="p-2 bg-red-900/40 border border-red-700 rounded text-red-300 text-xs">{deleteError}</div>
      {/if}

      <div class="flex justify-end gap-2 pt-1 border-t border-line">
        <button
          onclick={() => (deleteModalOpen = false)}
          class="px-3 py-1.5 text-xs text-ink-2 border border-line-2 hover:bg-surface-sunken rounded-lg transition-colors"
        >닫기</button>
        <button
          onclick={executeDeleteArtifact}
          disabled={!deletePreview?.can_delete || deleteSubmitting}
          class="px-3 py-1.5 text-xs text-red-300 border border-red-700/60 hover:bg-red-900/30 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg transition-colors"
        >
          {deleteSubmitting ? '삭제 중...' : '삭제 실행'}
        </button>
      </div>
    </div>
  {/if}
</Modal>
