## Implementation Tasks

- [x] Add a Kolla-volume directory preparation task before Afterglow service start, creating group-writable `afterglow_api` and `afterglow` directories without host bind mounts.
- [x] Configure the backend portable logger to write date-and-size sequenced files under `/var/log/kolla/afterglow_api`.
- [x] Run the frontend portable tee process with `/var/log/kolla/afterglow` as its component directory while preserving stdout and stderr.
- [x] Add and run Kolla contracts proving directory setup ordering, existing-volume mounts, backend sink, and frontend sink.
