FROM rockylinux:9

ARG VERSION=unknown
ARG SCM_REF=unknown
ARG SCM_REPOSITORY=https://github.com/nuxeo/nuxeo-drive.git
ARG DESCRIPTION="Image to build the Nuxeo Drive GNU/Linux binary."

LABEL description=${DESCRIPTION}
LABEL version=${VERSION}
LABEL scm-ref=${SCM_REF}
LABEL scm-url=${SCM_REPOSITORY}
LABEL maintainer="mschoentgen@nuxeo.com"

ENV BUILD_VERSION=${VERSION}
ENV GIT_URL=${SCM_REPOSITORY}
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=off

WORKDIR /opt

# Install required packages
RUN dnf install -y \
    dnf-plugins-core \
    file \
    gcc \
    git \
    make \
    wget \
    zip \
    desktop-file-utils \
    bzip2-devel \
    libffi-devel \
    openssl-devel \
    readline-devel \
    sqlite-devel \
    xz-devel \
    zlib-devel \
    mesa-libGL \
    dbus \
    patch \
    python3 \
    python3-devel \
    glibc-langpack-en \
    glibc-locale-source && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    dnf clean all

# Install the Python version needed by Nuxeo Drive
RUN git clone -b master $GIT_URL sources && \
    cd sources && \
    #git reset --hard ${SCM_REF} && \
    # Install Python
    WORKSPACE=/opt ./tools/linux/deploy_ci_agent.sh --install-python && \
    # Copy the entry point script
    cp tools/linux/entrypoint.sh / && \
    # Clean-up
    cd /opt && \
        # Delete the repository
        rm -rf /opt/sources && \
        # CPython-specific test files
        rm -rf /opt/deploy-dir/.pyenv/versions/*/lib/python*/test && \
    # Unused locales
    localedef -i en_US -f UTF-8 en_US.UTF-8 || true && \
    cp -f /usr/lib/locale/locale-archive /usr/lib/locale/locale-archive.tmpl || true && \
    localedef --list-archive | grep -v 'en_US.utf8' | xargs --no-run-if-empty localedef --delete-from-archive || true && \
    # Not more needed requirements
    dnf remove -y git && \
    dnf clean all

# Make entrypoint executable
RUN chmod a+x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

VOLUME ["/opt/dist", "/opt/sources"]
