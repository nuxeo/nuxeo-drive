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
    # Clean-up
        yum clean all

# Install the Python version needed by Nuxeo Drive
RUN git clone $GIT_URL sources && \
    cd sources && \
    git reset --hard ${SCM_REF} && \
    # Install Python
    WORKSPACE=/opt ./tools/linux/deploy_jenkins_slave.sh --install-python && \
    # Copy the entry point script
    cp tools/linux/entrypoint.sh / && \
    cd .. && \
    rm -rf sources

# Create the jenkins user (the same one as on our CI/QA setup)
RUN useradd -m -d /home/jenkins -u 1001 -s /bin/bash jenkins

# Adapt rights
RUN chown jenkins:jenkins -R /opt && \
    chown jenkins:jenkins /entrypoint.sh && \
    chmod a+x /entrypoint.sh

# The entry point will build Nuxeo Drive if called without argument.
# Else it will simply use the desired command line.
ENTRYPOINT ["/entrypoint.sh"]

# That folder has to be set by the caller, it will hold generated binaries
VOLUME ["/opt/dist"]

USER jenkins
