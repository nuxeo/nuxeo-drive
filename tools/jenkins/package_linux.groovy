#!groovy
// Script to build Nuxeo Drive package on GNU/Linux.
// An AppImage will be built from a specific docker image.

/*
Connect to the container:
    docker run -it --rm centos:7.2.151 /bin/bash

Retrieve a file:
    # docker cp CONTAINER:/nuxeo-drive/dist/nuxeo-drive-linux-4.1.4.zip .
    container_id="$(docker ps | grep centos:7.2.1511 | head -1 | cut -d" " -f1)"
    docker cp ${container_id}:/nuxeo-drive/dist/nuxeo-drive-linux-4.1.4.zip .
*/

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([[$class: 'GitHubPushTrigger']]),
    [$class: 'BuildDiscarderProperty', strategy:
        [$class: 'LogRotator', daysToKeepStr: '60', numToKeepStr: '60', artifactNumToKeepStr: '1']],
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false],
    [$class: 'ParametersDefinitionProperty', parameterDefinitions: [
        [$class: 'StringParameterDefinition',
            name: 'BRANCH_NAME',
            defaultValue: 'master']
    ]]
])

pipeline {
    agent {
        docker {
            label 'PUB_DEPLOY'
            image 'centos:7.2.1511'
            args '-u root --privileged'
        }
    }

    stages {
        stage('Checkout') {
            steps {
                sh 'rm -rf nuxeo-drive'
                sh 'yum install -y git-core'
                sh "git clone --branch ${env.BRANCH_NAME} --depth=1 https://github.com/nuxeo/nuxeo-drive.git"
            }
        }

        stage('Setup') {
            steps {
                // pyenv requirements
                // https://github.com/pyenv/pyenv/wiki/Common-build-problems#prerequisites
                sh 'yum install -y bzip2-devel libffi-devel openssl-devel readline-devel sqlite-devel xz-devel zlib-devel'

                // QtQuick requirements: OpenGL
                // https://access.redhat.com/solutions/56301
                sh 'yum install -y mesa-libGL'

                // General
                sh 'yum install -y file findutils gcc make wget zip'

                // Nuxeo Drive requirements
                dir('nuxeo-drive') {
                    sh 'WORKSPACE="$(pwd)" ./tools/linux/deploy_jenkins_slave.sh --install-release'
                }
            }
        }

        stage('Build') {
            steps {
                dir('nuxeo-drive') {
                    sh 'WORKSPACE="$(pwd)" ./tools/linux/deploy_jenkins_slave.sh --build'
                }
            }
        }

        stage('Archive') {
            steps {
                archiveArtifacts artifacts: 'nuxeo-drive/dist/*.zip', fingerprint: true
                archiveArtifacts artifacts: 'nuxeo-drive/dist/*.AppImage', fingerprint: true
            }
        }
    }
}
