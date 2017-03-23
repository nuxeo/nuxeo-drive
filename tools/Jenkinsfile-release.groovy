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
