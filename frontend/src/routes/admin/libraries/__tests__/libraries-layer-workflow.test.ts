// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const source = readFileSync(resolve(__dirname, '../+page.svelte'), 'utf8');
const navSource = readFileSync(resolve(__dirname, '../../../../lib/config/nav.ts'), 'utf8');
const fileStorageManageSource = readFileSync(
	resolve(__dirname, '../../../dashboard/file-storage/manage/+page.svelte'),
	'utf8'
);

describe('/admin/libraries layer workflow UI contract', () => {
	it('promotes the squashfs workflow copy and API prefix to Palimpsest layer management', () => {
		// 레이어드 VM 기능의 공식 명칭은 Palimpsest다 (docs/palimpsest.md). 이 페이지가 그 코어 UI다.
		expect(source).toContain('PageHeader title="Palimpsest 레이어 관리"');
		expect(source).not.toContain('squashfs 레이어 관리');
		expect(source).toContain('/api/v1/admin/libraries/build');
		expect(source).not.toContain('/api/v1/admin/layers');
	});

	it('keeps only one admin library navigation item and renames the file-storage manage page', () => {
		expect(navSource).not.toContain('squashfs 레이어');
		expect(navSource).toContain("label: 'Palimpsest'");
		expect(fileStorageManageSource).toContain('사전 빌드 파일 스토리지');
		expect(fileStorageManageSource).not.toContain('title="라이브러리 관리"');
	});

	it('offers Glance base image selectors for root system and NVIDIA builds', () => {
		expect(source).toContain('/api/v1/admin/libraries/base-images');
		expect(source).toContain('id="system-base-image"');
		expect(source).toContain('bind:value={systemForm.base_image_id}');
		expect(source).toContain('id="nvidia-base-image"');
		expect(source).toContain('bind:value={nvidiaForm.base_image_id}');
		expect(source).toContain('{baseImageLabel(image)}');
		expect(source).not.toContain('UBUNTU_BASE_OPTIONS');
	});

	it('sends base_image_id for root build payloads and inherits parents for child builds', () => {
		expect(source).toContain("{ layer_name: systemForm.layer_name, kind: 'uv', base_image_id: systemForm.base_image_id }");
		expect(source).toContain("{ layer_name: systemForm.layer_name, kind: 'system', apt_packages: aptPackages, base_image_id: systemForm.base_image_id }");
		expect(source).toContain("{ layer_name: nvidiaForm.layer_name, kind: 'nvidia', nvidia_driver_branch: branch, base_image_id: nvidiaForm.base_image_id }");
		expect(source).toContain("kind: 'python'");
		expect(source).toContain("kind: 'pip'");
		expect(source).toContain('상속 Ubuntu: {ubuntuBaseLabel(selectedPythonParentArtifact)}');
		expect(source).toContain('상속 Ubuntu: {ubuntuBaseLabel(selectedPackageParentArtifact)}');
	});

	it('surfaces mixed base image profile risk before save or consume', () => {
		expect(source).toContain('selectedProfileBaseImageIds');
		expect(source).toContain('profileHasMixedUbuntuBases');
		expect(source).toContain('consumeProfileHasMixedUbuntuBases');
		expect(source).toContain('base image가 섞여 있습니다');
		expect(source).toContain('소비 VM 이미지는 프로필 레이어가 저장한 Glance base image fingerprint에서 자동 결정됩니다');
		expect(source).toContain('표시는 base→상위 레이어 순서');
	});

	it('shows private-by-default publication controls for artifacts and profiles', () => {
		expect(source).toContain('/publication');
		expect(source).toContain('is_published');
		expect(source).toContain('setArtifactPublication');
		expect(source).toContain('setProfilePublication');
	});
	
	it('surfaces Dockerfile import workflow and polls active import jobs', () => {
		expect(source).toContain('GitHub Dockerfile import');
		expect(source).toContain('/api/v1/admin/libraries/imports/dockerfile');
		expect(source).toContain('activeImportJobs');
		expect(source).toContain('void loadImportJobs()');
	});

	it('supports multi-mode Dockerfile studio with URL fetch, file upload, templates, plan preview, and inline build', () => {
		expect(source).toContain('Palimpsest Dockerfile 빌드');
		expect(source).toContain('dockerfileMode');
		expect(source).toContain('/api/v1/palimpsest/builds/dockerfile/fetch-url');
		expect(source).toContain('/api/v1/palimpsest/builds/dockerfile/plan');
		expect(source).toContain('/api/v1/palimpsest/builds/dockerfile');
		expect(source).toContain('applyDockerfileTemplate');
		expect(source).toContain('handleDockerFileUpload');
		expect(source).toContain('previewDockerfilePlan');
		expect(source).toContain('submitInlineDockerfileBuild');
		expect(source).toContain('빌드 계획 미리보기');
	});

	it('wires completed Dockerfile build jobs and saved profiles to direct instance execution (consume)', () => {
		expect(source).toContain('launchConsumeWithProfile');
		expect(source).toContain('id="admin-library-consume"');
		expect(source).toContain('인스턴스 실행');
	});
});
