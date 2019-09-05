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

# Usefull envars
ENV BUILD_VERSION ${VERSION}
ENV GIT_URL ${SCM_REPOSITORY}
ENV WORKSPACE /opt

WORKDIR $WORKSPACE

# Install requirements
RUN rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7 && \
    yum install -y deltarpm && \
    yum install -y --setopt=tsflags=noscripts \
        # General
            file \
            findutils \
            gcc \
            git-core \
            make \
            wget \
            zip \
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
        # Needed by AppImage conformity tools
            desktop-file-utils \
            libappstream-glib \
            which && \
    # Clean-up
        yum clean all

# Install the Python version needed by Nuxeo Drive
RUN git clone $GIT_URL sources && \
    cd sources && \
    git reset --hard ${SCM_REF} && \
    # Install Python
    ./tools/linux/deploy_jenkins_slave.sh --install-python && \
    # Copy the entry point script
    cp tools/linux/entrypoint.sh / && \
    cd $WORKSPACE && \
    rm -rf sources

# Fix (appstream-util:5998): GLib-GIO-ERROR: No GSettings schemas are installed on the system
RUN glib-compile-schemas /usr/share/glib-2.0/schemas/

# Create the jenkins user (the same one as on our CI/QA setup)
RUN useradd -m -d /home/jenkins -u 1001 -s /bin/bash jenkins

# Create the shared folder and adapt rights
RUN mkdir "$WORKSPACE/dist" && \
    chown jenkins:jenkins -R $WORKSPACE && \
    chown jenkins:jenkins /entrypoint.sh && \
    chmod a+x /entrypoint.sh

# The entry point will build Nuxeo Drive if called without argument.
# Else it will simply use the desired command line.
ENTRYPOINT ["/entrypoint.sh"]

USER jenkins

# That folder has to be set by the caller, it will hold generated binaries
VOLUME ["$WORKSPACE/dist"]
