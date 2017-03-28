#!groovy
// Release
// Script to create a new beta or to deploy a release of Nuxeo Drive.

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    overrideIndexTriggers(true),
    pipelineTriggers([]),
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false],
    [$class: 'ParametersDefinitionProperty', parameterDefinitions: [
        [$class: 'ChoiceParameterDefinition',
            name: 'RELEASE_TYPE',
            choices: 'nightly\nbeta\nrelease']
    ]]
])

// Trigger the Drive nightly build job to build executables and have artifacts
triggerRemoteJob mode: [
        $class: 'TrackProgressAwaitResult',
        scheduledTimeout: [timeoutStr: '30m'],
        startedTimeout: [timeoutStr: '30m'],
        timeout: [timeoutStr: '1d'],
        whenFailure: [$class: 'StopAsFailure'],
        whenScheduledTimeout: [$class: 'StopAsFailure'],
        whenStartedTimeout: [$class: 'StopAsFailure'],
        whenTimeout: [$class: 'StopAsFailure'],
        whenUnstable: [$class: 'StopAsFailure']
    ],
    remotePathMissing: [$class: 'StopAsFailure'],
    remotePathUrl: 'jenkins://0ebd1d5127f055c8c674d7778f51ea00/Drive/Drive-nightly-build'


node('IT') {
    withEnv(["WORKSPACE=${pwd()}"]) {
        stage('Checkout') {
            checkout scm
        }
        stage('Deploy') {
            dir('build') {
                deleteDir()
            }
            dir('dist') {
                deleteDir()
            }
            sh 'tools/release_and_deploy.sh'
        }
    }
}
