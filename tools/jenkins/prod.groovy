#!groovy
// Script to deploy a release of Nuxeo Drive.

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([]),
    [$class: 'BuildDiscarderProperty', strategy:
        [$class: 'LogRotator', daysToKeepStr: '60', numToKeepStr: '60', artifactNumToKeepStr: '5']],
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false]
])


timestamps {
    node('IT') {
        withEnv(["WORKSPACE=${pwd()}"]) {
            stage('Checkout') {
                checkout scm
            }
            stage('Deploy') {
                sh 'tools/deploy.sh'
                archive 'prerelease.json'

                def release = sh script: 'git tag -l "release-*" --sort=-taggerdate | head -n1', returnStdout: true
                release = release.replace('release-', '').trim()
                currentBuild.description = "Release ${release}"
            }
        }
    }
}
