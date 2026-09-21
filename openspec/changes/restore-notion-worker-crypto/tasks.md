## 1. Dependency ownership

- [x] 1.1 Replace the remote backend crypto source with the repository-owned `services/afterglow-crypto` path source
- [x] 1.2 Add `afterglow-crypto` to the worker-only dependency group and refresh the lockfile
- [x] 1.3 Verify backend and worker dependency installs are regular, self-contained distributions

## 2. Image regression coverage

- [x] 2.1 Add a final-worker-image smoke that imports the crypto boundary and performs a Notion encryption round trip
- [x] 2.2 Expose the worker image smoke through the repository command surface
- [x] 2.3 Build the Linux amd64 worker image and prove the pre-deployment smoke succeeds
- [x] 2.4 Build the Linux amd64 backend image affected by the shared dependency source

## 3. Documentation and gates

- [x] 3.1 Document crypto package ownership, worker image invariants, and immutable Kolla rollout in architecture and deployment guidance
- [x] 3.2 Add the recovery to the changelog
- [x] 3.3 Run focused dependency, crypto, image, and Kolla contract checks
- [x] 3.4 Run `npm run test:gate`

## 4. Publication and production recovery

- [ ] 4.1 Commit and push the verified `dev` change to trigger the canonical image workflow
- [ ] 4.2 Wait for the Docker Build & Push workflow and resolve the worker manifest digest for the pushed commit
- [ ] 4.3 Validate and repair controller host trust without disabling SSH host verification
- [ ] 4.4 Pin only `afterglow_worker_image_ref` to the immutable worker digest
- [ ] 4.5 Run Kolla Afterglow prechecks and the service-scoped rollout from `/etc/kolla`
- [ ] 4.6 Verify intended controllers run the expected digest with stable process state and clean startup logs
- [ ] 4.7 Verify a successful Notion target cycle and an advancing `notion_targets.last_sync`

## 5. Completion

- [ ] 5.1 Archive the completed OpenSpec change
- [ ] 5.2 Commit and push the archive plus final documentation evidence
