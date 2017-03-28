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

def create_packages() {
    // Trigger the Drive nightly build job to build executables and have artifacts
    triggerRemoteJob
        parameterFactories: [[
            $class: 'CurrentBuild',
            excludesStr: '',
            includeSensitive: false]
        ],
        mode: [
            $class: 'TrackProgressAwaitResult',
            scheduledTimeout: [timeoutStr: '30m'],
            startedTimeout: [timeoutStr: '30m'],
            timeout: [timeoutStr: '2h'],
            whenFailure: [$class: 'StopAsFailure'],
            whenScheduledTimeout: [$class: 'StopAsFailure'],
            whenStartedTimeout: [$class: 'StopAsFailure'],
            whenTimeout: [$class: 'StopAsFailure'],
            whenUnstable: [$class: 'StopAsFailure']
        ],
        remotePathMissing: [$class: 'StopAsFailure'],
        remotePathUrl: 'jenkins://0ebd1d5127f055c8c674d7778f51ea00/Drive/Drive-packages'
}


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

            if (env.RELEASE_TYPE == 'beta') {
                sh 'tools/release.sh --create'

                echo 'Triggering the remote job "Drive-packages"'
                def commit_id = sh script: 'git tag -l "release-*" --sort=-taggerdate | head -n1', returnStdout: true
                param.BRANCH_NAME = commit_id
                env.BRANCH_NAME = commit_id
                create_packages()

                sh 'tools/release.sh --publish'
            } else if (env.RELEASE_TYPE == 'release') {
                sh 'tools/deploy.sh'
            }
        }
    }
}
