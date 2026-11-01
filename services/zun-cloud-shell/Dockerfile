# syntax=docker/dockerfile:1.7
# Canonical installed-native verification build. No network in any RUN.
# Prepare build-inputs/<arch> with prepare_build.py on each architecture builder.
# PYTHON_IMAGE must be an approved digest-pinned multi-arch Python 3.12 image
# containing git, cc/static libc, nsenter, iproute2 and the native libraries needed
# by the prepared wheels. It must NOT contain cloud credentials or Docker socket.
ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE} AS native
ARG PYTHON_IMAGE
RUN --network=none case "$PYTHON_IMAGE" in *@sha256:*) ;; *) echo 'PYTHON_IMAGE must be digest pinned' >&2; exit 1 ;; esac
ARG TARGETARCH
COPY build-inputs/${TARGETARCH} /opt/inputs
COPY pyproject.toml install.py prepare_build.py /opt/cloud-shell-native/
COPY afterglow_zun_cloud_shell /opt/cloud-shell-native/afterglow_zun_cloud_shell
COPY tests /opt/cloud-shell-native/tests
RUN --network=none python /opt/cloud-shell-native/prepare_build.py --verify /opt/inputs \
    && python -m pip install --no-index --find-links=/opt/inputs/wheels \
       --constraint /opt/inputs/upper-constraints.txt \
       --requirement /opt/inputs/zun/requirements.txt setuptools==80.9.0 wheel==0.45.1 pbr==7.0.1 \
    && cp -a /opt/inputs/zun /opt/patched-zun \
    && python /opt/cloud-shell-native/install.py /opt/patched-zun \
    && python -m pip install --no-index --find-links=/opt/inputs/wheels \
       --no-build-isolation --no-deps /opt/cloud-shell-native \
    && PBR_VERSION=16.0.0 python -m pip install --no-index \
       --find-links=/opt/inputs/wheels --no-build-isolation --no-deps /opt/patched-zun
WORKDIR /opt/acceptance
ENV EVENTLET_NO_GREENDNS=yes
CMD ["python", "-m", "unittest", "discover", "-s", "/opt/cloud-shell-native/tests", "-v"]
