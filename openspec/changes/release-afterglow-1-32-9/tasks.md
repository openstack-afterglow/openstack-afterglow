## Implementation Tasks
- [x] Freeze current public changes and review the 1.32.8-to-candidate release delta.
- [x] Synchronize canonical 1.32.9 metadata, changelog and architecture documentation.
- [x] Pass the complete canonical test:gate and actual runtime smoke for the final snapshot after review-blocker corrections.
- [x] Reproduce and correct fixed-admin catalog cleanup, editable row identity, secret reveal identity and cross-owner view-state release blockers.
- [ ] Commit the qualified snapshot on shared dev, preserve later concurrent work, and push normally.
- [ ] Verify exact-SHA GitHub CI success before creating the immutable 1.32.9 tag.
- [ ] Publish bilingual 1.32.9 release notes focused on the previous-release delta.
- [ ] Verify three release/latest image digests/revisions, runtime versions and Helm publication.
