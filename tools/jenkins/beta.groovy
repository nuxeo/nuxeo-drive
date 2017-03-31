#!groovy
// Script to create a new beta of Nuxeo Drive.

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([]),
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false],
    [$class: 'ParametersDefinitionProperty', parameterDefinitions: [
        [$class: 'BooleanParameterDefinition',
            name: 'DRY_RUN',
            defaultValue: false,
            description: 'Do nothing but checking the job actually works.']
    ]]
])

node('IT') {
    withEnv(["WORKSPACE=${pwd()}"]) {
        env.DRY_RUN = params.DRY_RUN

        stage('Checkout') {
            deleteDir()
            checkout scm
            checkout([
                $class: 'GitSCM', branches: [[name: '*/master']],
                extensions: [
                    [$class: 'CleanCheckout'],
                    [$class: 'LocalBranch', localBranch: 'master']]
            ])
        }

        stage('Create') {
            sh 'tools/release.sh --create'
        }

        stage('Trigger') {
            // Trigger the Drive packages job to build executables and have artifacts
            def commit_id = sh script: 'git tag -l "release-*" --sort=-taggerdate | head -n1', returnStdout: true
            build job: '/Drive/Drive-packages', parameters: [
                [$class: 'StringParameterValue', name: 'BRANCH_NAME', value: commit_id],
                [$class: 'BooleanParameterValue', name: 'CLEAN_WORKSPACE', value: true]]
        }

        stage('Publish') {
            dir('dist') {
                deleteDir()
            }
            sh 'tools/release.sh --publish'
        }
    }
}
