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
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';

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
    github_url: string;
    commit_sha: string;
    dockerfile_path: string;
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

  // ---------------------------------------------------------------------------
  // 빌드 폼
  // ---------------------------------------------------------------------------

  // System/tool 레이어 빌드 폼
  let systemForm = $state({ layer_name: '', apt_packages: '', base_image_id: '' });
  let systemSubmitting = $state(false);
  let nvidiaForm = $state({ layer_name: '', nvidia_driver_branch: '580', base_image_id: '' });
  let nvidiaSubmitting = $state(false);

  // Python runtime 레이어 빌드 폼
  let pythonForm = $state({ layer_name: '', python_version: '3.11', parent_artifact_id: '' });
  let pythonSubmitting = $state(false);

  // Python 패키지 레이어 빌드 폼
  let packageForm = $state({ layer_name: '', pip_packages: '', pip_index_url: '', pip_extra_index_urls: '', pip_find_links: '', parent_artifact_id: '' });
  let packageSubmitting = $state(false);

  const PIP_SPEC_RE = /^[A-Za-z0-9][A-Za-z0-9._\[\],<>=!~+*\-]*$/;
  const APT_PACKAGE_RE = /^[a-z0-9][a-z0-9.+-]*$/;
  const NVIDIA_DRIVER_BRANCHES = ['550', '570', '575', '580'];
  const VERSION_CLAUSE_PREFIX_RE = /^[<>=!~]/;
  const PIP_SOURCE_FORBIDDEN_RE = /[\r\n\t '"`$\\;|<>]/;

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
  let profileForm = $state({ name: '', selectedLayers: [] as string[] });
  let publicationUpdating = $state('');
  const profileNameValid = $derived(/^[a-z0-9][a-z0-9.+-]*$/.test(profileForm.name));
  // 봉인 완료된 artifact만 부모 후보로 사용
  const sealedArtifacts = $derived(artifacts.filter(a => a.is_sealed));
  const uvParentArtifacts = $derived(sealedArtifacts.filter(a => a.kind === 'uv'));
  const packageParentArtifacts = $derived(sealedArtifacts.filter(a => artifactLineageHasKind(a, 'python')));
  const selectedPythonParentArtifact = $derived(uvParentArtifacts.find(a => String(a.id) === pythonForm.parent_artifact_id));
  const selectedPackageParentArtifact = $derived(packageParentArtifacts.find(a => String(a.id) === packageForm.parent_artifact_id));
  const selectedProfileUbuntuBases = $derived(uniqueUbuntuBasesForLayerNames(profileForm.selectedLayers));
  const selectedProfileBaseImageIds = $derived(uniqueBaseImageIdsForLayerNames(profileForm.selectedLayers));
  const profileHasMixedUbuntuBases = $derived(selectedProfileUbuntuBases.length > 1 || selectedProfileBaseImageIds.length > 1);
  const packageSpecs = $derived(splitPackageSpecs(packageForm.pip_packages));
  const systemAptPackages = $derived(splitAptPackages(systemForm.apt_packages));
  const systemInvalidAptPackages = $derived(invalidAptPackages(systemForm.apt_packages));
  const nvidiaBranchValid = $derived(NVIDIA_DRIVER_BRANCHES.includes(nvidiaForm.nvidia_driver_branch.trim()));
  const packageInvalidSpecs = $derived(invalidPackageSpecs(packageForm.pip_packages));
  const packageExtraIndexUrls = $derived(splitUrlLines(packageForm.pip_extra_index_urls));
  const packageFindLinks = $derived(splitUrlLines(packageForm.pip_find_links));
  const packageInvalidUrls = $derived(invalidPipSourceUrls([
    packageForm.pip_index_url.trim(),
    ...packageExtraIndexUrls,
    ...packageFindLinks,
  ]));
  let profileSubmitting = $state(false);
  let profileMessage = $state('');
  let profileError = $state('');
  let profileDeletingName = $state('');
  let profileDeleteError = $state('');

  // ---------------------------------------------------------------------------
  // 소비 폼
  // ---------------------------------------------------------------------------

  let consumeForm = $state({
    profile_name: '',
    server_name: '',
    flavor_id: '',
    network_id: '',
    key_name: '',
    ssh_public_key: '',
    ssh_username: '',
  });
  let consumeSubmitting = $state(false);

  let importForm = $state({ github_url: '', ref: '', dockerfile_path: 'Dockerfile', layer_prefix: '', profile_name: '', base_image_id: '' });
  let importSubmitting = $state(false);

  let keypairs = $state<Keypair[]>([]);
  const selectedConsumeProfile = $derived(profiles.find(p => p.name === consumeForm.profile_name));
  const selectedConsumeProfileUbuntuBases = $derived(
    selectedConsumeProfile ? uniqueUbuntuBasesForLayerNames(selectedConsumeProfile.layers) : [],
  );
  const selectedConsumeProfileBaseImageIds = $derived(
    selectedConsumeProfile ? uniqueBaseImageIdsForLayerNames(selectedConsumeProfile.layers) : [],
  );
  const selectedConsumeProfileBaseImage = $derived(
    selectedConsumeProfileBaseImageIds.length === 1 ? baseImageForId(selectedConsumeProfileBaseImageIds[0]) : null,
  );
  const consumeProfileHasMixedUbuntuBases = $derived(selectedConsumeProfileUbuntuBases.length > 1 || selectedConsumeProfileBaseImageIds.length > 1);


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
      if (!systemForm.base_image_id && baseImages.length > 0) systemForm.base_image_id = baseImages[0].id;
      if (!nvidiaForm.base_image_id && baseImages.length > 0) nvidiaForm.base_image_id = baseImages[0].id;
      if (!importForm.base_image_id && baseImages.length > 0) importForm.base_image_id = baseImages[0].id;
    } catch {
      baseImages = [];
    }
  }

  async function loadImportJobs(refresh = true) {
    try {
      importJobs = await api.get<LayerImportJob[]>('/api/v1/admin/libraries/imports', token, projectId, { refresh });
    } catch {
      importJobs = [];
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
      if (activeImportJobs.length > 0) void loadImportJobs();
    }, activeBuilds.length > 0 || activeImportJobs.length > 0 ? 10_000 : 30_000);
    return () => clearInterval(interval);
  });

  $effect(() => {
    if (!token) return;
    untrack(() => loadAll());
  });
  // ---------------------------------------------------------------------------
  // 빌드 트리거
  // ---------------------------------------------------------------------------

  async function triggerUvBuild() {
    if (systemSubmitting) return;
    systemSubmitting = true;
    error = '';
    message = '';
    try {
      const result = await api.post<{ build_id: number; layer_name: string; status: string }>(
        '/api/v1/admin/libraries/build',
        { layer_name: systemForm.layer_name, kind: 'uv', base_image_id: systemForm.base_image_id },
        token,
        projectId,
      );
      message = `uv 레이어 빌드 시작 (ID: ${result.build_id}, 레이어: ${result.layer_name})`;
      await Promise.allSettled([loadBuilds(true), loadArtifacts(true)]);
    } catch (e) {
      error = e instanceof ApiError ? `빌드 트리거 실패: ${e.message}` : '네트워크 오류';
    } finally {
      systemSubmitting = false;
    }
  }

  async function triggerSystemAptBuild() {
    if (systemSubmitting) return;
    const aptPackages = splitAptPackages(systemForm.apt_packages);
    const invalidPackages = aptPackages.filter(pkg => !APT_PACKAGE_RE.test(pkg));
    if (aptPackages.length === 0) {
      error = 'apt 패키지를 1개 이상 입력하세요';
      return;
    }
    if (invalidPackages.length > 0) {
      error = `apt 패키지명 형식 오류: ${invalidPackages.join(', ')}`;
      return;
    }
    systemSubmitting = true;
    error = '';
    message = '';
    try {
      const result = await api.post<{ build_id: number; layer_name: string; status: string }>(
        '/api/v1/admin/libraries/build',
        { layer_name: systemForm.layer_name, kind: 'system', apt_packages: aptPackages, base_image_id: systemForm.base_image_id },
        token,
        projectId,
      );
      message = `apt system 레이어 빌드 시작 (ID: ${result.build_id}, 레이어: ${result.layer_name})`;
      await Promise.allSettled([loadBuilds(true), loadArtifacts(true)]);
    } catch (e) {
      error = e instanceof ApiError ? `빌드 트리거 실패: ${e.message}` : '네트워크 오류';
    } finally {
      systemSubmitting = false;
    }
  }

  async function triggerNvidiaDriverBuild() {
    if (nvidiaSubmitting) return;
    const branch = nvidiaForm.nvidia_driver_branch.trim();
    if (!nvidiaForm.layer_name) {
      error = 'NVIDIA 레이어 이름을 입력하세요';
      return;
    }
    if (!nvidiaBranchValid) {
      error = `NVIDIA 드라이버 브랜치는 ${NVIDIA_DRIVER_BRANCHES.join(', ')} 중 하나여야 합니다`;
      return;
    }
    nvidiaSubmitting = true;
    error = '';
    message = '';
    try {
      const result = await api.post<{ build_id: number; layer_name: string; status: string }>(
        '/api/v1/admin/libraries/build',
        { layer_name: nvidiaForm.layer_name, kind: 'nvidia', nvidia_driver_branch: branch, base_image_id: nvidiaForm.base_image_id },
        token,
        projectId,
      );
      message = `NVIDIA 드라이버 템플릿 레이어 빌드 시작 (ID: ${result.build_id}, 레이어: ${result.layer_name}, branch: ${branch})`;
      await Promise.allSettled([loadBuilds(true), loadArtifacts(true)]);
    } catch (e) {
      error = e instanceof ApiError ? `빌드 트리거 실패: ${e.message}` : '네트워크 오류';
    } finally {
      nvidiaSubmitting = false;
    }
  }

  async function triggerPythonBuild() {
    if (pythonSubmitting) return;
    pythonSubmitting = true;
    error = '';
    message = '';
    try {
      const result = await api.post<{ build_id: number; layer_name: string; parent_artifact_id: number | null; status: string }>(
        '/api/v1/admin/libraries/build',
        {
          layer_name: pythonForm.layer_name,
          kind: 'python',
          python_version: pythonForm.python_version,
          parent_artifact_id: Number(pythonForm.parent_artifact_id),
        },
        token,
        projectId,
      );
      message = `Python runtime 레이어 빌드 시작 (ID: ${result.build_id}, 레이어: ${result.layer_name}, 부모 ID: ${result.parent_artifact_id})`;
      await Promise.allSettled([loadBuilds(true), loadArtifacts(true)]);
    } catch (e) {
      error = e instanceof ApiError ? `빌드 트리거 실패: ${e.message}` : '네트워크 오류';
    } finally {
      pythonSubmitting = false;
    }
  }

  async function triggerPackageBuild() {
    if (packageSubmitting) return;
    const specs = splitPackageSpecs(packageForm.pip_packages);
    const invalidSpecs = specs.filter(spec => !PIP_SPEC_RE.test(spec));
    const pipIndexUrl = packageForm.pip_index_url.trim();
    const pipExtraIndexUrls = splitUrlLines(packageForm.pip_extra_index_urls);
    const pipFindLinks = splitUrlLines(packageForm.pip_find_links);
    const invalidUrls = invalidPipSourceUrls([pipIndexUrl, ...pipExtraIndexUrls, ...pipFindLinks]);
    if (specs.length === 0) {
      error = '패키지 스펙을 1개 이상 입력하세요';
      return;
    }
    if (invalidSpecs.length > 0) {
      error = `패키지 스펙 형식 오류: ${invalidSpecs.join(', ')}`;
      return;
    }
    if (invalidUrls.length > 0) {
      error = `pip source URL 형식 오류: ${invalidUrls.join(', ')}`;
      return;
    }
    packageSubmitting = true;
    error = '';
    message = '';
    try {
      const body: Record<string, unknown> = {
        layer_name: packageForm.layer_name,
        kind: 'pip',
        pip_packages: specs,
        parent_artifact_id: Number(packageForm.parent_artifact_id),
      };
      if (pipIndexUrl) body.pip_index_url = pipIndexUrl;
      if (pipExtraIndexUrls.length > 0) body.pip_extra_index_urls = pipExtraIndexUrls;
      if (pipFindLinks.length > 0) body.pip_find_links = pipFindLinks;
      const result = await api.post<{ build_id: number; layer_name: string; parent_artifact_id: number | null; status: string }>(
        '/api/v1/admin/libraries/build',
        body,
        token,
        projectId,
      );
      message = `Python 패키지 레이어 빌드 시작 (ID: ${result.build_id}, 레이어: ${result.layer_name}, 부모 ID: ${result.parent_artifact_id})`;
      await Promise.allSettled([loadBuilds(true), loadArtifacts(true)]);
    } catch (e) {
      error = e instanceof ApiError ? `빌드 트리거 실패: ${e.message}` : '네트워크 오류';
    } finally {
      packageSubmitting = false;
    }
  }

  async function upsertProfile() {
    if (profileSubmitting) return;
    if (profileHasMixedUbuntuBases) {
      profileError = `base image가 섞인 프로필은 저장할 수 없습니다: ${selectedProfileBaseImageIds.join(', ') || selectedProfileUbuntuBases.join(', ')}`;
      return;
    }
    profileSubmitting = true;
    profileError = '';
    profileMessage = '';
    try {
      const layers = normalizeProfileLayers(profileForm.selectedLayers);
      const result = await api.post<{ id: number; name: string; layers: string[] }>(
        '/api/v1/admin/libraries/profiles',
        { name: profileForm.name, layers },
        token,
        projectId,
      );
      profileMessage = `프로필 '${result.name}' 저장 완료 (레이어: ${result.layers.join(', ')})`;
      profileForm.selectedLayers = result.layers;
      await loadProfiles(true);
    } catch (e) {
      profileError = e instanceof ApiError ? `프로필 저장 실패: ${e.message}` : '네트워크 오류';
    } finally {
      profileSubmitting = false;
    }
  }

  function uniqueLayerNames(layers: string[]): string[] {
    const seen = new Set<string>();
    const result: string[] = [];
    for (const layer of layers) {
      if (seen.has(layer)) continue;
      seen.add(layer);
      result.push(layer);
    }
    return result;
  }

  function lineageNamesForArtifact(artifact: LayerArtifact | ArtifactSummary): string[] {
    const chain = 'lineage' in artifact && artifact.lineage?.length
      ? artifact.lineage
      : [artifact as ArtifactSummary];
    return uniqueLayerNames(chain.map(node => node.name));
  }

  function lineageNamesForLayerName(layerName: string): string[] {
    const artifact = sealedArtifacts.find(a => a.name === layerName);
    return artifact ? lineageNamesForArtifact(artifact) : [layerName];
  }

  function normalizeProfileLayers(layers: string[]): string[] {
    const expanded: string[] = [];
    for (const layer of layers) {
      expanded.push(...lineageNamesForLayerName(layer));
    }
    return uniqueLayerNames(expanded);
  }

  function selectedLayerDependsOn(layerName: string, ancestorName: string): boolean {
    const lineage = lineageNamesForLayerName(layerName);
    const ancestorIndex = lineage.indexOf(ancestorName);
    const layerIndex = lineage.lastIndexOf(layerName);
    return ancestorIndex >= 0 && layerIndex >= 0 && ancestorIndex < layerIndex;
  }

  function removeProfileLayerCascade(layerName: string) {
    profileForm.selectedLayers = normalizeProfileLayers(
      profileForm.selectedLayers.filter(
        selected => selected !== layerName && !selectedLayerDependsOn(selected, layerName),
      ),
    );
  }

  function toggleProfileArtifact(artifact: LayerArtifact) {
    if (profileForm.selectedLayers.includes(artifact.name)) {
      removeProfileLayerCascade(artifact.name);
      return;
    }
    profileForm.selectedLayers = normalizeProfileLayers([
      ...profileForm.selectedLayers,
      ...lineageNamesForArtifact(artifact),
    ]);
  }

  function isAutoIncludedParent(layerName: string): boolean {
    return profileForm.selectedLayers.some(
      selected => selected !== layerName && selectedLayerDependsOn(selected, layerName),
    );
  }

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
      if (profileForm.name === profile.name) {
        profileForm.name = '';
        profileForm.selectedLayers = [];
      }
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

  // ---------------------------------------------------------------------------
  // 소비 인스턴스 생성
  // ---------------------------------------------------------------------------

  async function triggerConsume() {
    if (consumeSubmitting) return;
    if (consumeProfileHasMixedUbuntuBases) {
      error = `선택한 프로필의 Ubuntu base가 섞여 있습니다: ${selectedConsumeProfileUbuntuBases.join(', ')}`;
      return;
    }
    consumeSubmitting = true;
    error = '';
    message = '';
    try {
      const body: Record<string, string> = {
        profile_name: consumeForm.profile_name,
        server_name: consumeForm.server_name,
        flavor_id: consumeForm.flavor_id,
      };
      if (consumeForm.network_id) body.network_id = consumeForm.network_id;
      if (consumeForm.key_name) body.key_name = consumeForm.key_name;
      if (consumeForm.ssh_public_key.trim()) body.ssh_public_key = consumeForm.ssh_public_key.trim();
      if (consumeForm.ssh_username) body.ssh_username = consumeForm.ssh_username;

      const result = await api.post<{ consume_id: number; server_id: string; status: string }>(
        '/api/v1/admin/libraries/consume',
        body,
        token,
        projectId,
      );
      const sshSource = consumeForm.ssh_public_key
        ? '직접 입력 공개키'
        : (consumeForm.key_name || '');
      const sshNote = sshSource
        ? `, SSH key=${sshSource}${consumeForm.ssh_username ? `, user=${consumeForm.ssh_username}` : ', user=기본 이미지 사용자'}`
        : '';
      message = `소비 인스턴스 생성됨 (ID: ${result.consume_id}, 서버: ${result.server_id?.slice(0, 8)}…${sshNote}). 내부 네트워크 IP는 상세에서 확인하세요.`;
      await loadConsumes(true);
    } catch (e) {
      error = e instanceof ApiError ? `소비 인스턴스 생성 실패: ${e.message}` : '네트워크 오류';
    } finally {
      consumeSubmitting = false;
    }
  }

  async function submitDockerfileImport() {
    if (importSubmitting) return;
    importSubmitting = true;
    error = '';
    message = '';
    try {
      const body: Record<string, string> = {
        github_url: importForm.github_url.trim(),
        dockerfile_path: importForm.dockerfile_path.trim() || 'Dockerfile',
        layer_prefix: importForm.layer_prefix.trim(),
        base_image_id: importForm.base_image_id,
      };
      if (importForm.ref.trim()) body.ref = importForm.ref.trim();
      if (importForm.profile_name.trim()) body.profile_name = importForm.profile_name.trim();
      const result = await api.post<LayerImportJob>('/api/v1/admin/libraries/imports/dockerfile', body, token, projectId);
      message = `Dockerfile import 시작 (ID: ${result.id}, profile: ${result.profile_name})`;
      await Promise.allSettled([loadImportJobs(true), loadBuilds(true), loadArtifacts(true), loadProfiles(true)]);
    } catch (e) {
      error = e instanceof ApiError ? `Dockerfile import 실패: ${e.message}` : '네트워크 오류';
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

  function uniqueBaseImageIdsForLayerNames(layers: string[]): string[] {
    const ids = new Set<string>();
    for (const layerName of normalizeProfileLayers(layers)) {
      const artifact = sealedArtifacts.find(a => a.name === layerName);
      if (artifact?.base_image_id) ids.add(artifact.base_image_id);
    }
    return [...ids].sort();
  }

  function uniqueUbuntuBasesForLayerNames(layers: string[]): string[] {
    const bases = new Set<string>();
    for (const layerName of normalizeProfileLayers(layers)) {
      const artifact = sealedArtifacts.find(a => a.name === layerName);
      if (artifact) bases.add(normalizeUbuntuBase(artifact.ubuntu_base));
    }
    return [...bases].sort();
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

  function artifactLineageHasKind(artifact: LayerArtifact | ArtifactSummary, kind: string): boolean {
    const chain = 'lineage' in artifact && artifact.lineage?.length
      ? artifact.lineage
      : [artifact as ArtifactSummary];
    return chain.some(node => node.kind === kind);
  }


  function shouldSplitPackageComma(raw: string, index: number): boolean {
    const rest = raw.slice(index).trimStart();
    return /^[A-Za-z0-9]/.test(rest) && !VERSION_CLAUSE_PREFIX_RE.test(rest);
  }

  function splitPackageSpecs(raw: string): string[] {
    const specs: string[] = [];
    let current = '';
    let bracketDepth = 0;
    for (let i = 0; i < raw.length; i += 1) {
      const ch = raw[i];
      if (ch === '[') bracketDepth += 1;
      if (ch === ']') bracketDepth = Math.max(0, bracketDepth - 1);
      if (ch === '\r' || ch === '\n' || (ch === ',' && bracketDepth === 0 && shouldSplitPackageComma(raw, i + 1))) {
        if (current.trim()) specs.push(current.trim());
        current = '';
        if (ch === '\r' && raw[i + 1] === '\n') i += 1;
        continue;
      }
      current += ch;
    }
    if (current.trim()) specs.push(current.trim());
    return specs;
  }

  function invalidPackageSpecs(raw: string): string[] {
    return splitPackageSpecs(raw).filter(spec => !PIP_SPEC_RE.test(spec));
  }

  function splitAptPackages(raw: string): string[] {
    return raw.split(/[\s,]+/).map(pkg => pkg.trim()).filter(Boolean);
  }

  function invalidAptPackages(raw: string): string[] {
    return splitAptPackages(raw).filter(pkg => !APT_PACKAGE_RE.test(pkg));
  }

  function splitUrlLines(raw: string): string[] {
    return raw.split(/\r?\n/).map(url => url.trim()).filter(Boolean);
  }

  function isValidPipSourceUrl(raw: string): boolean {
    if (!raw) return true;
    if (PIP_SOURCE_FORBIDDEN_RE.test(raw)) return false;
    try {
      const url = new URL(raw);
      return (url.protocol === 'http:' || url.protocol === 'https:')
        && Boolean(url.hostname)
        && !url.username
        && !url.password
        && !url.search
        && !url.hash;
    } catch {
      return false;
    }
  }

  function invalidPipSourceUrls(urls: string[]): string[] {
    return urls.filter(url => url && !isValidPipSourceUrl(url));
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
  <PageHeader title="Palimpsest 레이어 관리" breadcrumb="Palimpsest">
    {#snippet actions()}
      <TutorialStartButton tour="admin-library" compactOnMobile />
      <button
        onclick={() => loadAll(true)}
        class="text-xs text-ink-2 hover:text-ink-0 transition-colors px-3 py-1.5 rounded border border-line-2 hover:border-line-2"
      >새로고침</button>
    {/snippet}
  </PageHeader>
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
    <div class="grid grid-cols-1 xl:grid-cols-3 gap-6 mb-8" data-tour="admin-library-ready">
      <!-- ------------------------------------------------------------------ -->
      <!-- System/tool 레이어 빌드                                             -->
      <!-- ------------------------------------------------------------------ -->
      <section class="bg-surface-sunken border border-line-2 rounded-xl p-5" data-tour="admin-library-system">
        <h2 class="text-sm font-semibold text-ink-0 mb-1">System/tool 레이어</h2>
        <p class="text-xs text-ink-2 mb-4">
          uv preset은 Python runtime 부모로 쓰는 curl-installed uv tool 레이어를 만들고,
          apt package layer는 apt로 설치 가능한 시스템 패키지를 캡처합니다.
          NVIDIA template은 소비 VM 부팅 시 해당 커널에 맞춰 open DKMS 드라이버를 설치하는 hook 레이어입니다.
        </p>
        <div class="space-y-3">
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="system-layer-name">레이어 이름 *</label>
            <input
              id="system-layer-name"
              type="text"
              placeholder="예: uv 또는 sys-tools"
              bind:value={systemForm.layer_name}
              class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
            />
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="system-base-image">Glance base image *</label>
            <select
              id="system-base-image"
              bind:value={systemForm.base_image_id}
              class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
            >
              {#each baseImages as image}
                <option value={image.id}>{baseImageLabel(image)}</option>
              {/each}
            </select>
            <p class="mt-1 text-[11px] text-ink-3">uv preset과 apt system layer는 선택한 실제 Glance image fingerprint를 저장합니다.</p>
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="system-apt-packages">apt 패키지 (system layer)</label>
            <textarea
              id="system-apt-packages"
              rows="3"
              placeholder="curl, nfs-common squashfs-tools"
              bind:value={systemForm.apt_packages}
              class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
            ></textarea>
            {#if systemInvalidAptPackages.length > 0}
              <p class="mt-1 text-[11px] text-red-300">apt 패키지명 형식 오류: {systemInvalidAptPackages.join(', ')}</p>
            {:else if systemAptPackages.length > 0}
              <p class="mt-1 text-[11px] text-ink-3">전송 예정: {systemAptPackages.join(', ')}</p>
            {/if}
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <button
              onclick={triggerUvBuild}
              disabled={systemSubmitting || !systemForm.layer_name || !systemForm.base_image_id}
              class="w-full py-2 px-4 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 disabled:cursor-not-allowed text-action-on-warm text-sm font-medium rounded-lg transition-colors"
            >
              {systemSubmitting ? '빌드 시작 중...' : 'uv preset 빌드'}
            </button>
            <button
              onclick={triggerSystemAptBuild}
              disabled={systemSubmitting || !systemForm.layer_name || !systemForm.base_image_id || systemAptPackages.length === 0 || systemInvalidAptPackages.length > 0}
              class="w-full py-2 px-4 bg-emerald-700 hover:bg-emerald-600 disabled:bg-surface-selected disabled:text-ink-3 disabled:cursor-not-allowed text-ink-0 text-sm font-medium rounded-lg transition-colors"
            >
              {systemSubmitting ? '빌드 시작 중...' : 'apt package layer 빌드'}
            </button>
          </div>
          <div class="mt-4 border-t border-line-2 pt-4 space-y-3">
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="nvidia-layer-name">NVIDIA 템플릿 레이어 이름 *</label>
              <input
                id="nvidia-layer-name"
                type="text"
                placeholder="예: nvidia-driver-580"
                bind:value={nvidiaForm.layer_name}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
              />
            </div>
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="nvidia-base-image">Glance base image *</label>
              <select
                id="nvidia-base-image"
                bind:value={nvidiaForm.base_image_id}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
              >
                {#each baseImages as image}
                  <option value={image.id}>{baseImageLabel(image)}</option>
                {/each}
              </select>
              <p class="mt-1 text-[11px] text-ink-3">NVIDIA hook 레이어도 선택한 실제 Glance image 계열의 소비 VM에서만 사용하세요.</p>
            </div>
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="nvidia-driver-branch">NVIDIA driver branch</label>
              <select
                id="nvidia-driver-branch"
                bind:value={nvidiaForm.nvidia_driver_branch}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
              >
                {#each NVIDIA_DRIVER_BRANCHES as branch}
                  <option value={branch}>{branch}</option>
                {/each}
              </select>
              <p class="mt-1 text-[11px] text-ink-3">
                레이어 자체에는 /usr hook만 저장하고, 소비 VM에서 cuda-keyring + nvidia-dkms-*-open을 설치합니다.
              </p>
            </div>
            <button
              onclick={triggerNvidiaDriverBuild}
              disabled={nvidiaSubmitting || !nvidiaForm.layer_name || !nvidiaForm.base_image_id || !nvidiaBranchValid}
              class="w-full py-2 px-4 bg-purple-700 hover:bg-purple-600 disabled:bg-surface-selected disabled:text-ink-3 disabled:cursor-not-allowed text-ink-0 text-sm font-medium rounded-lg transition-colors"
            >
              {nvidiaSubmitting ? '빌드 시작 중...' : 'NVIDIA driver template 빌드'}
            </button>
          </div>
        </div>
      </section>

      <!-- ------------------------------------------------------------------ -->
      <!-- GitHub Dockerfile import                                           -->
      <!-- ------------------------------------------------------------------ -->
      <section class="bg-surface-sunken border border-line-2 rounded-xl p-5" data-tour="admin-library-import">
        <h2 class="text-sm font-semibold text-ink-0 mb-1">GitHub Dockerfile import</h2>
        <p class="text-xs text-ink-2 mb-4">
          GitHub repository의 pinned commit Dockerfile을 지원되는 RUN/COPY/ADD/WORKDIR/ENV subset으로 squashfs layer chain과 profile로 가져옵니다.
        </p>
        <div class="space-y-3">
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
              <label class="block text-xs text-ink-2 mb-1" for="dockerfile-ref">Commit SHA / ref *</label>
              <input
                id="dockerfile-ref"
                type="text"
                placeholder="40자 commit SHA 권장"
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
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="dockerfile-base-image">Glance base image *</label>
            <select
              id="dockerfile-base-image"
              bind:value={importForm.base_image_id}
              class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
            >
              {#each baseImages as image}
                <option value={image.id}>{baseImageLabel(image)}</option>
              {/each}
            </select>
          </div>
          <button
            onclick={submitDockerfileImport}
            disabled={importSubmitting || !importForm.github_url.trim() || !importForm.layer_prefix.trim() || !importForm.base_image_id}
            class="w-full py-2 px-4 bg-sky-700 hover:bg-sky-600 disabled:bg-surface-selected disabled:text-ink-3 disabled:cursor-not-allowed text-ink-0 text-sm font-medium rounded-lg transition-colors"
          >
            {importSubmitting ? 'Import 시작 중...' : 'Dockerfile import 시작'}
          </button>
          {#if importJobs.length > 0}
            <div class="border border-line-2 rounded-lg overflow-hidden">
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
                      <td class="px-3 py-2 text-ink-2">#{job.id}</td>
                      <td class="px-3 py-2 font-mono">{job.profile_name}</td>
                      <td class="px-3 py-2 text-ink-2">{job.base_image_name || shortId(job.base_image_id)}</td>
                      <td class="px-3 py-2"><StatusChip status={job.status} /></td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </div>
      </section>

      <!-- ------------------------------------------------------------------ -->
      <!-- Python runtime 레이어 빌드                                         -->
      <!-- ------------------------------------------------------------------ -->
      <section class="bg-surface-sunken border border-line-2 rounded-xl p-5" data-tour="admin-library-python">
        <h2 class="text-sm font-semibold text-ink-0 mb-1">Python runtime 레이어</h2>
        <p class="text-xs text-ink-2 mb-4">
          uv 레이어 위에 CPython runtime만 추가합니다. pip 패키지는 별도 패키지 레이어에서 설치합니다.
        </p>
        <div class="space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="python-layer-name">레이어 이름 *</label>
              <input
                id="python-layer-name"
                type="text"
                placeholder="예: python311"
                bind:value={pythonForm.layer_name}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
              />
            </div>
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="python-ver">Python 버전 *</label>
              <input
                id="python-ver"
                type="text"
                placeholder="3.11"
                bind:value={pythonForm.python_version}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
              />
            </div>
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="python-parent">부모 uv 레이어 *</label>
            {#if uvParentArtifacts.length > 0}
              <select
                id="python-parent"
                bind:value={pythonForm.parent_artifact_id}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-indigo-500"
              >
                <option value="">uv 레이어를 선택하세요</option>
                {#each uvParentArtifacts as a}
                  <option value={String(a.id)}>#{a.id} {artifactChainLabel(a)} ({fmtRelative(a.created_at)})</option>
                {/each}
              </select>
            {:else}
              <div class="text-xs text-ink-3 italic px-3 py-2 bg-surface-base border border-line-2 rounded-lg">
                먼저 uv 레이어를 빌드하세요
              </div>
            {/if}
          </div>
          {#if selectedPythonParentArtifact}
            <div class="px-3 py-2 bg-indigo-900/20 border border-indigo-700/40 rounded-lg space-y-1">
              <div class="text-xs text-indigo-300">
                stacked 빌드: <span class="font-mono">{artifactChainLabel(selectedPythonParentArtifact)}</span> → <span class="font-mono">{pythonForm.layer_name || '(새 레이어)'}</span>
              </div>
              <p class="text-[11px] text-indigo-200/70">부모 uv artifact ID #{selectedPythonParentArtifact.id} 위에 Python runtime delta만 생성합니다.</p>
              <p class="text-[11px] text-indigo-200/70">상속 Ubuntu: {ubuntuBaseLabel(selectedPythonParentArtifact)}</p>
            </div>
          {/if}
          <button
            onclick={triggerPythonBuild}
            disabled={pythonSubmitting || !pythonForm.layer_name || !pythonForm.python_version || !pythonForm.parent_artifact_id}
            class="w-full py-2 px-4 bg-indigo-600 hover:bg-indigo-500 disabled:bg-surface-selected disabled:text-ink-3 disabled:cursor-not-allowed text-ink-0 text-sm font-medium rounded-lg transition-colors"
          >
            {pythonSubmitting ? '빌드 시작 중...' : 'Python runtime 레이어 빌드'}
          </button>
        </div>
      </section>

      <!-- ------------------------------------------------------------------ -->
      <!-- Python 패키지 레이어 빌드                                           -->
      <!-- ------------------------------------------------------------------ -->
      <section class="bg-surface-sunken border border-line-2 rounded-xl p-5">
        <h2 class="text-sm font-semibold text-ink-0 mb-1">Python 패키지 레이어</h2>
        <p class="text-xs text-ink-2 mb-4">
          Python lineage가 포함된 부모 위에 pip 패키지만 추가합니다. 버전 pin과 안전한 constraint만 허용됩니다.
        </p>
        <div class="space-y-3">
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="package-layer-name">레이어 이름 *</label>
            <input
              id="package-layer-name"
              type="text"
              placeholder="예: scientific-py"
              bind:value={packageForm.layer_name}
              class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
            />
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="package-parent">부모 Python lineage 레이어 *</label>
            {#if packageParentArtifacts.length > 0}
              <select
                id="package-parent"
                bind:value={packageForm.parent_artifact_id}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-indigo-500"
              >
                <option value="">Python lineage 레이어를 선택하세요</option>
                {#each packageParentArtifacts as a}
                  <option value={String(a.id)}>#{a.id} {artifactChainLabel(a)} ({a.kind}{a.python_version ? ` · py${a.python_version}` : ''} · {fmtRelative(a.created_at)})</option>
                {/each}
              </select>
            {:else}
              <div class="text-xs text-ink-3 italic px-3 py-2 bg-surface-base border border-line-2 rounded-lg">
                먼저 Python runtime 레이어를 빌드하세요
              </div>
            {/if}
          </div>
          {#if selectedPackageParentArtifact}
            <div class="px-3 py-2 bg-indigo-900/20 border border-indigo-700/40 rounded-lg space-y-1">
              <div class="text-xs text-indigo-300">
                package delta: <span class="font-mono">{artifactChainLabel(selectedPackageParentArtifact)}</span> → <span class="font-mono">{packageForm.layer_name || '(새 레이어)'}</span>
              </div>
              <p class="text-[11px] text-indigo-200/70">부모 artifact ID #{selectedPackageParentArtifact.id}의 Python runtime을 재사용합니다.</p>
              <p class="text-[11px] text-indigo-200/70">상속 Ubuntu: {ubuntuBaseLabel(selectedPackageParentArtifact)}</p>
            </div>
          {/if}
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="package-pip">pip 패키지 스펙 *</label>
            <textarea
              id="package-pip"
              rows="3"
              placeholder="numpy==1.26.4, pandas==2.2.2, scikit-learn==1.5.1&#10;numpy>=1.24,<2"
              bind:value={packageForm.pip_packages}
              class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
            ></textarea>
            {#if packageInvalidSpecs.length > 0}
              <p class="mt-1 text-[11px] text-red-300">패키지 스펙 형식 오류: {packageInvalidSpecs.join(', ')}</p>
            {:else if packageSpecs.length > 0}
              <p class="mt-1 text-[11px] text-ink-3">전송 예정: {packageSpecs.join(', ')}</p>
            {/if}
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="package-index-url">pip index URL (선택)</label>
            <input
              id="package-index-url"
              type="url"
              placeholder="https://download.pytorch.org/whl/cpu"
              bind:value={packageForm.pip_index_url}
              class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
            />
            <p class="mt-1 text-[11px] text-ink-3">pip install --index-url 값입니다. 인증정보, query, fragment는 허용하지 않습니다.</p>
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="package-extra-index-urls">extra index URLs (선택, 줄당 1개)</label>
            <textarea
              id="package-extra-index-urls"
              rows="2"
              placeholder="https://pypi.org/simple"
              bind:value={packageForm.pip_extra_index_urls}
              class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
            ></textarea>
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="package-find-links">find-links URLs (선택, 줄당 1개)</label>
            <textarea
              id="package-find-links"
              rows="2"
              placeholder="https://download.pytorch.org/whl/cpu/torch_stable.html"
              bind:value={packageForm.pip_find_links}
              class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
            ></textarea>
            {#if packageInvalidUrls.length > 0}
              <p class="mt-1 text-[11px] text-red-300">pip source URL 형식 오류: {packageInvalidUrls.join(', ')}</p>
            {:else if packageForm.pip_index_url.trim() || packageExtraIndexUrls.length > 0 || packageFindLinks.length > 0}
              <p class="mt-1 text-[11px] text-ink-3">pip source 옵션을 빌드에 함께 전달합니다.</p>
            {/if}
          </div>
          <button
            onclick={triggerPackageBuild}
            disabled={packageSubmitting || !packageForm.layer_name || !packageForm.parent_artifact_id || packageSpecs.length === 0 || packageInvalidSpecs.length > 0 || packageInvalidUrls.length > 0}
            class="w-full py-2 px-4 bg-purple-600 hover:bg-purple-500 disabled:bg-surface-selected disabled:text-ink-3 disabled:cursor-not-allowed text-ink-0 text-sm font-medium rounded-lg transition-colors"
          >
            {packageSubmitting ? '빌드 시작 중...' : 'Python 패키지 레이어 빌드'}
          </button>
        </div>
      </section>

      <!-- ------------------------------------------------------------------ -->
      <!-- 소비 인스턴스 생성                                                  -->
      <!-- ------------------------------------------------------------------ -->
      <section class="bg-surface-sunken border border-line-2 rounded-xl p-5">
        <h2 class="text-sm font-semibold text-ink-0 mb-1">소비 인스턴스 생성</h2>
        <p class="text-xs text-ink-2 mb-4">
          프로필의 레이어 체인을 각자 별도 NFS share에서 RO 마운트하고
          OverlayFS로 합성한 VM을 생성합니다.
        </p>
        <div class="space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="consume-profile">프로필 *</label>
              {#if profiles.length > 0}
                <select
                  id="consume-profile"
                  bind:value={consumeForm.profile_name}
                  class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
                >
                  <option value="">선택하세요</option>
                  {#each profiles as p}
                    <option value={p.name}>{p.name} ({p.layers.length}개 레이어)</option>
                  {/each}
                </select>
              {:else}
                <input
                  id="consume-profile"
                  type="text"
                  placeholder="프로필 이름"
                  bind:value={consumeForm.profile_name}
                  class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
                />
              {/if}
              {#if selectedConsumeProfileBaseImage}
                <p class="mt-1 text-[11px] text-ink-3">기본 이미지: {baseImageLabel(selectedConsumeProfileBaseImage)} 사용</p>
              {:else if selectedConsumeProfileBaseImageIds.length === 1}
                <p class="mt-1 text-[11px] text-ink-3">기본 이미지 ID: {shortId(selectedConsumeProfileBaseImageIds[0])} 사용</p>
              {:else if consumeProfileHasMixedUbuntuBases}
                <p class="mt-1 text-[11px] text-yellow-300">base image가 섞인 프로필입니다: {selectedConsumeProfileBaseImageIds.join(', ') || selectedConsumeProfileUbuntuBases.join(', ')}</p>
              {/if}
            </div>
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="server-name">서버 이름 *</label>
              <input
                id="server-name"
                type="text"
                placeholder="layer-consumer-01"
                bind:value={consumeForm.server_name}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
              />
            </div>
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="flavor-id">Flavor ID *</label>
            <input
              id="flavor-id"
              type="text"
              placeholder="flavor UUID 또는 이름"
              bind:value={consumeForm.flavor_id}
              class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
            />
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="network-id">Network ID (선택)</label>
            <input
              id="network-id"
              type="text"
              placeholder="기본 네트워크"
              bind:value={consumeForm.network_id}
              class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
            />
            <p class="mt-1 text-[11px] text-ink-3">소비 VM 이미지는 프로필 레이어가 저장한 Glance base image fingerprint에서 자동 결정됩니다.</p>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="consume-keypair">접속 키페어 (선택)</label>
              <select
                id="consume-keypair"
                bind:value={consumeForm.key_name}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
              >
                <option value="">선택 안 함</option>
                {#each keypairs as kp}
                  <option value={kp.name}>{kp.name}</option>
                {/each}
              </select>
              <p class="mt-1 text-[11px] text-ink-3">현재 로그인한 프로젝트/사용자 범위에서 보이는 키페어만 선택됩니다.</p>
            </div>
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="consume-ssh-username">SSH 사용자 (선택)</label>
              <input
                id="consume-ssh-username"
                type="text"
                placeholder="비우면 이미지 기본 사용자"
                bind:value={consumeForm.ssh_username}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
              />
              <p class="mt-1 text-[11px] text-ink-3">키나 공개키를 넣은 경우에만 사용됩니다. VM에는 Floating IP를 붙이지 않으므로 내부 IP로 접속해야 합니다.</p>
            </div>
          </div>
          <div>
            <label class="block text-xs text-ink-2 mb-1" for="consume-ssh-public-key">SSH 공개키 직접 입력 (선택)</label>
            <textarea
              id="consume-ssh-public-key"
              rows="3"
              placeholder="다른 사용자의 공개키를 직접 붙여넣을 때 사용"
              bind:value={consumeForm.ssh_public_key}
              class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm font-mono resize-none"
            ></textarea>
            <p class="mt-1 text-[11px] text-ink-3">직접 입력한 공개키가 있으면 위 키페어 선택보다 우선합니다.</p>
          </div>
          <button
            onclick={triggerConsume}
            disabled={consumeSubmitting || !consumeForm.profile_name || !consumeForm.server_name || !consumeForm.flavor_id || consumeProfileHasMixedUbuntuBases}
            class="w-full py-2 px-4 bg-purple-600 hover:bg-purple-500 disabled:bg-surface-selected disabled:text-ink-3 disabled:cursor-not-allowed text-ink-0 text-sm font-medium rounded-lg transition-colors"
          >
            {consumeSubmitting ? '인스턴스 생성 중...' : '소비 인스턴스 생성'}
          </button>
        </div>
      </section>
    </div>

    <!-- ---------------------------------------------------------------------- -->
    <!-- 프로필 구성 카드                                                        -->
    <!-- ---------------------------------------------------------------------- -->
    <div class="mb-8">
      <section class="bg-surface-sunken border border-line-2 rounded-xl p-5" data-tour="admin-library-profile">
        <h2 class="text-sm font-semibold text-ink-0 mb-1">프로필 구성</h2>
        <p class="text-xs text-ink-2 mb-4">
          빌드된 레이어를 순서대로 묶어 named 프로필로 저장합니다.
          소비 인스턴스는 이 프로필의 레이어 스택을 OverlayFS로 마운트합니다.
          <span class="text-ink-3">(표시는 base→상위 레이어 순서, 소비 시 topmost 우선순위로 변환)</span>
        </p>
        {#if profileError}
          <div class="mb-3 p-2 bg-red-900/40 border border-red-700 rounded text-red-300 text-xs">{profileError}</div>
        {/if}
        {#if profileDeleteError}
          <div class="mb-3 p-2 bg-red-900/40 border border-red-700 rounded text-red-300 text-xs">{profileDeleteError}</div>
        {/if}
        {#if profileMessage}
          <div class="mb-3 p-2 bg-green-900/40 border border-green-700 rounded text-green-300 text-xs">{profileMessage}</div>
        {/if}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p class="text-xs text-ink-3 mb-2">빌드된 레이어 (클릭해 선택)</p>
            {#if artifacts.length === 0}
              <p class="text-xs text-ink-3 italic">아직 빌드된 레이어가 없습니다</p>
            {:else}
              <div class="space-y-1 max-h-40 overflow-y-auto">
                {#each artifacts as a}
                  {@const selected = profileForm.selectedLayers.includes(a.name)}
                  <button
                    type="button"
                    onclick={() => toggleProfileArtifact(a)}
                    disabled={!a.is_sealed}
                    title={!a.is_sealed ? '봉인 전 — 빌드 완료 후 사용 가능' : artifactChainLabel(a)}
                    class="w-full text-left px-3 py-2 rounded-lg text-xs transition-colors
                      {!a.is_sealed ? 'opacity-40 cursor-not-allowed bg-surface-base border border-line text-ink-3' :
                       selected ? 'bg-action-warm/50 border border-action-warm text-action-on-warm' :
                       'bg-surface-base border border-line-2 text-ink-2 hover:border-line-2'}"
                  >
                    <div class="flex items-center gap-2">
                      <span class="font-mono flex-1">#{a.id} {a.name}</span>
                      <span class="text-[10px] px-1.5 py-0.5 rounded {a.kind === 'uv' ? 'bg-surface-selected/60 text-action-warm' : 'bg-indigo-900/60 text-indigo-300'}">{a.kind}</span>
                      {#if selected}
                        <span class="text-[10px] text-action-warm">#{profileForm.selectedLayers.indexOf(a.name) + 1}</span>
                      {/if}
                    </div>
                    <div class="mt-1 text-[10px] text-ink-3 truncate">체인: {artifactChainLabel(a)}</div>
                    <div class="mt-0.5 text-[10px] text-ink-3 truncate">Ubuntu: {ubuntuBaseLabel(a)}</div>
                    {#if packageLabel(a) !== '—'}
                      <div class="mt-0.5 text-[10px] text-ink-3 truncate">요청 패키지: {packageLabel(a)}</div>
                    {/if}
                  </button>
                {/each}
              </div>
            {/if}
          </div>
          <div class="space-y-3">
            <div>
              <p class="text-xs text-ink-3 mb-1">선택된 레이어 순서</p>
              {#if profileForm.selectedLayers.length === 0}
                <p class="text-xs text-ink-3 italic">레이어를 선택하세요</p>
              {:else}
                <div class="space-y-1">
                  {#each profileForm.selectedLayers as layer, i}
                    <div class="flex items-center gap-2 text-xs text-ink-2 px-2 py-1 bg-surface-base rounded">
                      <span class="text-ink-3 w-4 text-right">{i + 1}</span>
                      <div class="flex-1 min-w-0">
                        <span class="font-mono">{layer}</span>
                        {#if isAutoIncludedParent(layer)}
                          <span class="ml-2 text-[10px] text-action-warm">상위 부모 자동 포함</span>
                        {/if}
                      </div>
                      <button type="button" onclick={() => removeProfileLayerCascade(layer)} class="text-ink-3 hover:text-red-400 transition-colors">✕</button>
                    </div>
                  {/each}
                </div>
              {/if}
              {#if selectedProfileBaseImageIds.length === 1}
                <p class="mt-2 text-[11px] text-ink-3">프로필 base image: {artifactBaseImageLabel(sealedArtifacts.find(a => a.base_image_id === selectedProfileBaseImageIds[0]) ?? { ubuntu_base: selectedProfileUbuntuBases[0], base_image_id: selectedProfileBaseImageIds[0] })}</p>
              {:else if profileHasMixedUbuntuBases}
                <div class="mt-2 px-3 py-2 bg-yellow-900/30 border border-yellow-700/50 rounded text-xs text-yellow-200">
                  base image가 섞여 있습니다: {selectedProfileBaseImageIds.join(', ') || selectedProfileUbuntuBases.join(', ')}. 저장/소비 전 같은 Glance base image 레이어만 선택하세요.
                </div>
              {/if}
            </div>
            <div>
              <label class="block text-xs text-ink-2 mb-1" for="profile-name-input">프로필 이름 *</label>
              <input
                id="profile-name-input"
                type="text"
                placeholder="예: default"
                pattern="[a-z0-9][a-z0-9.+-]*"
                bind:value={profileForm.name}
                class="w-full bg-surface-base border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
              />
              {#if profileForm.name && !profileNameValid}
                <p class="mt-1 text-xs text-red-400">소문자, 숫자, 점, 하이픈만 사용할 수 있습니다. 예: base-uv</p>
              {/if}
            </div>
            <button
              onclick={upsertProfile}
              disabled={profileSubmitting || !profileForm.name || !profileNameValid || profileForm.selectedLayers.length === 0 || profileHasMixedUbuntuBases}
              class="w-full py-2 px-4 bg-teal-700 hover:bg-teal-600 disabled:bg-surface-selected disabled:text-ink-3 disabled:cursor-not-allowed text-ink-0 text-sm font-medium rounded-lg transition-colors"
            >
              {profileSubmitting ? '저장 중...' : '프로필 저장'}
            </button>
            {#if profiles.length > 0}
              <div class="pt-3 border-t border-line-2">
                <p class="text-xs text-ink-3 mb-2">저장된 프로필</p>
                <div class="overflow-x-auto border border-line-2 rounded-lg">
                  <table class="w-full text-xs">
                    <thead>
                      <tr class="text-ink-3 bg-surface-base/80">
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
                            <span class="{profile.is_published ? 'text-action-warm' : 'text-ink-3'}">{profile.is_published ? '공개' : '비공개'}</span>
                          </td>
                          <td class="px-3 py-2">
                            <div class="flex justify-end gap-2">
                              <button
                                type="button"
                                onclick={() => {
                                  profileForm.name = profile.name;
                                  profileForm.selectedLayers = normalizeProfileLayers(profile.layers);
                                  profileDeleteError = '';
                                }}
                                class="px-2 py-1 rounded border border-line-2 text-ink-2 hover:border-gray-400 transition-colors"
                              >
                                불러오기
                              </button>
                              <button
                                type="button"
                                onclick={() => setProfilePublication(profile, !profile.is_published)}
                                disabled={publicationUpdating === `profile:${profile.name}`}
                                class="px-2 py-1 rounded border border-action-warm text-action-warm hover:border-action-warm disabled:border-line-2 disabled:text-ink-3 disabled:cursor-not-allowed transition-colors"
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
          </div>
        </div>
      </section>
    </div>

    <!-- ---------------------------------------------------------------------- -->
    <!-- 아티팩트 현황 / 삭제                                                    -->
    <!-- ---------------------------------------------------------------------- -->
    <div class="mb-6" data-tour="admin-library-artifacts">
      <h3 class="text-xs font-semibold text-ink-2 uppercase tracking-wide mb-2">아티팩트 현황</h3>
      {#if artifacts.length === 0}
        <div class="bg-surface-sunken border border-line-2 rounded-xl p-6 text-center text-ink-3 text-sm">
          생성된 artifact가 없습니다
        </div>
      {:else}
        <div class="bg-surface-sunken border border-line-2 rounded-xl overflow-hidden">
          <div class="max-h-80 overflow-y-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-xs text-ink-3 uppercase tracking-wide sticky top-0 z-10 bg-surface-sunken [box-shadow:inset_0_-1px_0_#374151]">
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
                      <div class="mt-1 flex items-center gap-1.5 text-[10px] text-ink-3">
                        <span class="px-1.5 py-0.5 rounded {a.kind === 'uv' ? 'bg-surface-selected/60 text-action-warm' : 'bg-indigo-900/60 text-indigo-300'}">{a.kind}</span>
                        {#if a.python_version}<span>py{a.python_version}</span>{/if}
                        <span>{a.is_sealed ? 'sealed' : 'unsealed'}</span>
                      </div>
                      <div class="mt-0.5 text-[10px] text-ink-3 truncate" title={ubuntuBaseLabel(a)}>Ubuntu: {ubuntuBaseLabel(a)}</div>
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
                        class="mr-3 text-xs {a.is_published ? 'text-action-warm hover:text-action-warm-hover' : 'text-ink-2 hover:text-ink-0'} disabled:text-ink-3 disabled:cursor-not-allowed transition-colors"
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
          <span class="ml-2 text-action-warm normal-case">(10초마다 자동 갱신)</span>
        {/if}
      </h3>
      {#if builds.length === 0}
        <div class="bg-surface-sunken border border-line-2 rounded-xl p-6 text-center text-ink-3 text-sm">
          빌드 기록이 없습니다
        </div>
      {:else}
        <div class="bg-surface-sunken border border-line-2 rounded-xl overflow-hidden">
          <div class="max-h-72 overflow-y-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-xs text-ink-3 uppercase tracking-wide sticky top-0 z-10 bg-surface-sunken [box-shadow:inset_0_-1px_0_#374151]">
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
                        <div class="mt-0.5 text-[10px] text-ink-3 truncate" title={buildPackageLabel(build)}>{buildPackageLabel(build)}</div>
                      {/if}
                    </td>
                    <td class="px-4 py-2.5 text-ink-2 text-xs font-mono hidden sm:table-cell">
                      <span class="text-[10px] px-1.5 py-0.5 rounded mr-1 {build.kind === 'uv' ? 'bg-surface-selected/60 text-action-warm' : 'bg-indigo-900/60 text-indigo-300'}">{build.kind ?? 'python'}</span>
                      {build.python_version ?? ''}
                      <div class="mt-0.5 text-[10px] text-ink-3 truncate" title={ubuntuBaseLabel(build)}>Ubuntu: {ubuntuBaseLabel(build)}</div>
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
                        <span class="text-xs text-ink-3 w-8 text-right">{build.progress_pct}%</span>
                      </div>
                    </td>
                    <td class="px-4 py-2.5 text-ink-3 text-xs font-mono hidden xl:table-cell">
                      {build.server_id ? build.server_id.slice(0, 8) + '…' : '—'}
                    </td>
                    <td class="px-4 py-2.5 text-ink-3 text-xs hidden lg:table-cell">
                      {fmtRelative(build.started_at)}
                    </td>
                    <td class="px-4 py-2.5 text-right">
                      <button
                        onclick={(e) => { e.stopPropagation(); openBuildDetail(build); }}
                        class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
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
        <div class="bg-surface-sunken border border-line-2 rounded-xl p-6 text-center text-ink-3 text-sm">
          생성된 소비 인스턴스가 없습니다
        </div>
      {:else}
        <div class="bg-surface-sunken border border-line-2 rounded-xl overflow-hidden">
          <div class="max-h-72 overflow-y-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-xs text-ink-3 uppercase tracking-wide sticky top-0 z-10 bg-surface-sunken [box-shadow:inset_0_-1px_0_#374151]">
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
                    <td class="px-4 py-2.5 text-ink-3 text-xs font-mono hidden xl:table-cell">
                      {c.server_id ? c.server_id.slice(0, 8) + '…' : '—'}
                    </td>
                    <td class="px-4 py-2.5 text-ink-3 text-xs hidden lg:table-cell">
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
          <p class="text-xs text-ink-3 mb-1">레이어 빌드 상세</p>
          <h2 class="text-base font-semibold text-ink-0">{buildDetail?.layer_name ?? '—'}</h2>
          {#if buildDetail}
            <p class="text-xs text-ink-3 mt-0.5">Ubuntu: {ubuntuBaseLabel(buildDetail)}</p>
          {/if}
          <p class="text-xs text-ink-3 mt-0.5">Kind: {buildDetail?.kind ?? '—'}{buildDetail?.python_version ? ` · Python ${buildDetail.python_version}` : ''}</p>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          {#if buildDetail?.status}
            <StatusChip status={buildDetail.status} />
          {/if}
          <button
            onclick={() => (detailOpen = false)}
            class="text-ink-3 hover:text-ink-0 transition-colors ml-2"
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
            <p class="text-ink-3 mb-0.5">VM 인스턴스</p>
            <p class="text-ink-0 font-mono truncate">{buildDetail.server_id ? buildDetail.server_id.slice(0, 18) + '…' : '—'}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-3 mb-0.5">VM 상태</p>
            {#if buildDetail.vm_status}
              <StatusChip status={buildDetail.vm_status.toLowerCase()} />
            {:else}
              <p class="text-ink-2">—</p>
            {/if}
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-3 mb-0.5">VM IP</p>
            <p class="text-ink-0 font-mono">{buildDetail.vm_ip ?? '—'}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-3 mb-0.5">경과 시간</p>
            <p class="text-ink-0">{elapsed(buildDetail.started_at)}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-3 mb-0.5">시작 시각</p>
            <p class="text-ink-0">{fmtDate(buildDetail.started_at)}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-3 mb-0.5">완료 시각</p>
            <p class="text-ink-0">{fmtDate(buildDetail.completed_at)}</p>
          </div>
          {#if buildDetail.share_id}
            <div class="col-span-2 bg-surface-sunken/60 rounded-lg px-3 py-2.5">
              <p class="text-ink-3 mb-0.5">NFS Share ID</p>
              <p class="text-ink-0 font-mono text-[11px] truncate">{buildDetail.share_id}</p>
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
            <p class="text-xs text-ink-3">
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
                class="text-[11px] text-action-warm hover:text-action-warm-hover transition-colors"
              >새로고침</button>
            {/if}
          </div>
          {#if buildDetail.live_console || buildDetail.console_log_excerpt}
            <pre class="bg-surface-canvas text-[11px] text-ink-2 font-mono whitespace-pre-wrap break-all overflow-auto max-h-56 rounded-lg p-3 border border-line">{buildDetail.live_console || buildDetail.console_log_excerpt}</pre>
          {:else}
            <div class="bg-surface-canvas rounded-lg p-3 border border-line text-[11px] text-ink-3 font-mono">
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
          <p class="text-xs text-ink-3 mb-1">소비 인스턴스 상세</p>
          <h2 class="text-base font-semibold text-ink-0">{consumeDetail?.server_name ?? '—'}</h2>
          <p class="text-xs text-ink-3 mt-0.5">프로필: {consumeDetail?.profile_name ?? '—'}</p>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          {#if consumeDetail?.status}
            <StatusChip status={consumeDetail.status} />
          {/if}
          <button
            onclick={() => (consumeDetailOpen = false)}
            class="text-ink-3 hover:text-ink-0 transition-colors ml-2"
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
            <p class="text-ink-3 mb-0.5">서버 ID</p>
            <p class="text-ink-0 font-mono truncate">{consumeDetail.server_id ? consumeDetail.server_id.slice(0, 18) + '…' : '—'}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-3 mb-0.5">VM 상태</p>
            {#if consumeDetail.vm_status}
              <StatusChip status={consumeDetail.vm_status.toLowerCase()} />
            {:else}
              <p class="text-ink-2">—</p>
            {/if}
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-3 mb-0.5">VM IP</p>
            <p class="text-ink-0 font-mono">{consumeDetail.vm_ip ?? '—'}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-3 mb-0.5">생성 시각</p>
            <p class="text-ink-0">{fmtDate(consumeDetail.created_at)}</p>
          </div>
          {#if consumeDetail.share_id}
            <div class="col-span-2 bg-surface-sunken/60 rounded-lg px-3 py-2.5">
              <p class="text-ink-3 mb-0.5">NFS Share ID (RO)</p>
              <p class="text-ink-0 font-mono text-[11px] truncate">{consumeDetail.share_id}</p>
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
          <p class="text-xs text-ink-3 mb-1">Artifact 삭제 미리보기</p>
          <h2 class="text-base font-semibold text-ink-0">
            {deletePreview ? `#${deletePreview.artifact.id} ${deletePreview.artifact.name}` : '조회 중'}
          </h2>
          <p class="text-xs text-ink-3 mt-0.5">삭제는 leaf artifact만 허용됩니다. 이름 기반 프로필 참조는 보수적으로 차단합니다.</p>
        </div>
        <button
          onclick={() => (deleteModalOpen = false)}
          class="text-ink-3 hover:text-ink-0 transition-colors"
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
            <p class="text-ink-3 mb-1">상속 체인</p>
            <p class="text-ink-0 font-mono break-all">{deletePreview.lineage.map(a => `${a.name}#${a.id}`).join(' → ')}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-3 mb-1">Ubuntu base</p>
            <p class="text-ink-0 break-all">{ubuntuBaseLabel(deletePreview.artifact)}</p>
          </div>
          <div class="bg-surface-sunken/60 rounded-lg px-3 py-2.5">
            <p class="text-ink-3 mb-1">요청 패키지</p>
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
                    <p class="mt-1 text-[11px] text-ink-3 font-mono break-all">{JSON.stringify(blocker.items)}</p>
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
