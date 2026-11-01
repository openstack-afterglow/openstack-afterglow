# syntax=docker/dockerfile:1.7
# Build context services/zun-cloud-shell. Supply the same approved digest-pinned
# architecture-neutral compiler image used to prepare the offline wheelhouse.
ARG COMPILER_IMAGE
FROM ${COMPILER_IMAGE} AS compile
ARG COMPILER_IMAGE
RUN case "$COMPILER_IMAGE" in *@sha256:*) ;; *) exit 1 ;; esac
COPY sandbox/pause.c /src/pause.c
RUN cc -static -Os -fstack-protector-strong -Wl,-z,relro,-z,now -o /pause /src/pause.c \
    && strip /pause
FROM scratch
COPY --from=compile /pause /pause
USER 65534:65534
ENTRYPOINT ["/pause"]
