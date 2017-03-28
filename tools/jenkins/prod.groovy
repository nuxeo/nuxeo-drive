#!groovy
// Script to deploy a release of Nuxeo Drive.

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([]),
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false],
])


node('IT') {
    withEnv(["WORKSPACE=${pwd()}"]) {
        stage('Checkout') {
            checkout scm
        }
        stage('Deploy') {
            sh 'tools/deploy.sh'
        }
    }
}
