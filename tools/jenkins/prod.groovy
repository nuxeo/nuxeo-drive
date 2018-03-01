#!groovy
// Script to deploy a release of Nuxeo Drive.

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([]),
    [$class: 'BuildDiscarderProperty', strategy:
        [$class: 'LogRotator', daysToKeepStr: '60', numToKeepStr: '60', artifactNumToKeepStr: '1']],
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false],
    [$class: 'ParametersDefinitionProperty', parameterDefinitions: [
        [$class: 'StringParameterDefinition',
            name: 'VERSION',
            defaultValue: 'x.y.z',
            description: 'The beta version to release.']
    ]]
])


timestamps {
    node('IT') {
        withEnv(["WORKSPACE=${pwd()}"]) {
            stage('Checkout') {
                checkout scm
            }

            stage('Deploy') {
                sh "tools/deploy.sh ${env.VERSION}""
                archive 'prerelease.json'
                currentBuild.description = "Release ${env.VERSION}"
            }
        }
    }
}
