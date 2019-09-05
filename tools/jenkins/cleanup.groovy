#!groovy
// Script to delete old alpha releases of Nuxeo Drive.

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([[$class: 'TimerTrigger', spec: '0 8 * * *']]),  // cronjob like everyday at 08:00am
    [$class: 'BuildDiscarderProperty', strategy:
        [$class: 'LogRotator', daysToKeepStr: '60', numToKeepStr: '60', artifactNumToKeepStr: '1']],
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false]
])


node('IT') {
    def credential_id = '4691426b-aa51-428b-901d-4e851ee37b01'

    withEnv(["WORKSPACE=${pwd()}"]) {
        stage('Checkout') {
            deleteDir()
            git credentialsId: credential_id, url: 'git@github.com:nuxeo/nuxeo-drive.git', branch: 'master'
        }

        stage('Clean-up') {
            sshagent([credential_id]) {
                sh "tools/cleanup.sh"
            }
        }
    }
}
