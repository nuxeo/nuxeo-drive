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

timestamps {
    node('IT') {
        withEnv(["WORKSPACE=${pwd()}"]) {
            env.DRY_RUN = params.DRY_RUN
            def credential_id = '4691426b-aa51-428b-901d-4e851ee37b01'
            def release = ''

            stage('Checkout') {
                deleteDir()
                git credentialsId: credential_id, url: 'ssh://git@github.com/nuxeo/nuxeo-drive.git'
            }

            stage('Create') {
                sshagent([credential_id]) {
                    sh 'tools/release.sh --create'
                }
            }

            stage('Trigger') {
                // Trigger the Drive packages job to build executables and have artifacts
                release = sh script: 'git tag -l "release-*" --sort=-taggerdate | head -n1', returnStdout: true
                release = release.trim()
                /*build job: '/Drive/Drive-packages', parameters: [
                    [$class: 'StringParameterValue', name: 'BRANCH_NAME', value: 'refs/tags/' + release],
                    [$class: 'BooleanParameterValue', name: 'CLEAN_WORKSPACE', value: true]]*/
            }

            stage('Publish') {
                dir('dist') {
                    deleteDir()
                }
                sshagent([credential_id]) {
                    sh 'tools/release.sh --publish'
                }
                release -= 'release-'
                currentBuild.description = "Beta ${release}"
            }
        }
    }
}
