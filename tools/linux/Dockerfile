FROM centos:7.2.1511

ARG VERSION=unknown
ARG SCM_REF=unknown
ARG SCM_REPOSITORY=https://github.com/nuxeo/nuxeo-drive.git
ARG DESCRIPTION="Image to build the Nuxeo Drive GNU/Linux binary."

LABEL description=${DESCRIPTION}
LABEL version=${VERSION}
LABEL scm-ref=${SCM_REF}
LABEL scm-url=${SCM_REPOSITORY}
LABEL maintainer="mschoentgen@nuxeo.com"

# Useful envars
ENV BUILD_VERSION ${VERSION}
ENV GIT_URL ${SCM_REPOSITORY}
ENV PIP_DISABLE_PIP_VERSION_CHECK "1"
ENV PIP_NO_CACHE_DIR "off"

WORKDIR /opt

# Install requirements
RUN rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7 && \
    yum install -y deltarpm && \
    yum install -y --setopt=tsflags=noscripts \
        # General
            file \
            gcc \
            git-core \
            make \
            wget \
            zip \
        # AppImage validity requirements
            desktop-file-utils \
        # pyenv requirements
        # https://github.com/pyenv/pyenv/wiki/Common-build-problems#prerequisites
            bzip2-devel \
            libffi-devel \
            openssl-devel \
            readline-devel \
            sqlite-devel \
            xz-devel \
            zlib-devel \
        # QtQuick requirements: OpenGL
        # https://access.redhat.com/solutions/56301
            mesa-libGL \
        # Qt requirements
            dbus \
        && \
    # Clean-up
    yum clean all

# Install the Python version needed by Nuxeo Drive
RUN git clone $GIT_URL sources && \
    cd sources && \
    git reset --hard ${SCM_REF} && \
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
            build-locale-archive && \
            localedef --list-archive | grep -v 'en_US.utf8' | xargs localedef --delete-from-archive && \
            /bin/cp -f /usr/lib/locale/locale-archive /usr/lib/locale/locale-archive.tmpl && \
            build-locale-archive && \
        # Not more needed requirements
            yum erase -y git-core && \
            yum clean all

# Create the travis user (the same one as on GitHub-CI)
RUN useradd -m -d /home/travis -u 1001 -s /bin/bash travis

# Adapt rights
RUN chown travis:travis -R /opt && \
    chown travis:travis /entrypoint.sh && \
    chmod a+x /entrypoint.sh

# The entry point will build Nuxeo Drive if called without argument.
# Else it will simply use the desired command line.
ENTRYPOINT ["/entrypoint.sh"]

# Folder has to be set by the caller:
#   /opt/dist will hold generated binaries
#   /opt/sources is Nuxeo Drive sources (git)
VOLUME ["/opt/dist", "/opt/sources"]

USER travis
