#!groovy
// Script to delete old alpha releases of Nuxeo Drive.

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([]),
    [$class: 'BuildDiscarderProperty', strategy:
        [$class: 'LogRotator', daysToKeepStr: '60', numToKeepStr: '60', artifactNumToKeepStr: '1']],
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
                sh "tools/cleanup.sh"
            }
        }
    }
}
