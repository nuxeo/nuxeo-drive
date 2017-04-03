#!groovy
// Script to deploy a release of Nuxeo Drive.

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([]),
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

                def release = sh script: 'git tag -l "release-*" --sort=-taggerdate | head -n1', returnStdout: true
                release = release.replace('release-', '').trim()
                currentBuild.description = "Release ${release}"
            }
        }
    }
}
