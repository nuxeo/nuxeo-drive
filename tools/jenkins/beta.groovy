#!groovy
// Script to create a new beta of Nuxeo Drive.

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
            name: 'BRANCH_NAME',
            defaultValue: 'master',
            description: 'The branch to checkout.'],
        [$class: 'ChoiceParameterDefinition',
            name: 'CHANNEL',
            choices: 'beta\nalpha']
    ]]
])

timestamps {
    node('IT') {
        def credential_id = '4691426b-aa51-428b-901d-4e851ee37b01'
        def differ_commits = '0'
        def release = ''
        def release_type = env.CHANNEL == 'beta' ? 'release' : 'alpha'

        try {
            stage('Checkout') {
                deleteDir()
                git credentialsId: credential_id, url: 'git@github.com:nuxeo/nuxeo-drive.git', branch: env.BRANCH_NAME
            }

            stage('Create') {
                if (release_type == 'alpha') {
                    release = sh script: "git tag -l 'alpha-*' --sort=-taggerdate | head -n1", returnStdout: true
                    release = release.trim()
                    differ_commits = sh script: "git describe --always --match='alpha-*' | cut -d'-' -f3", returnStdout: true
                    differ_commits = differ_commits.trim()
                    if (release == '' || differ_commits == '0') {
                        currentBuild.description = 'Skip: no new commit'
                        currentBuild.result = 'ABORTED'
                        return
                    }
                }

                sshagent([credential_id]) {
                    sh "tools/release.sh --create ${release_type}"
                    archiveArtifacts artifacts: 'draft.json', fingerprint: true, allowEmptyArchive: true
                }
            }

            stage('Trigger') {
                // Trigger the Drive packages job to build executables and have artifacts
                release = sh script: "git tag -l '${release_type}-*' --sort=-taggerdate | head -n1", returnStdout: true
                release = release.trim()
                build job: 'Drive-packages', parameters: [
                    [$class: 'StringParameterValue', name: 'BRANCH_NAME', value: 'refs/tags/' + release],
                    [$class: 'BooleanParameterValue', name: 'CLEAN_WORKSPACE', value: true]]
            }

            stage('Publish') {
                dir('build') {
                    deleteDir()
                }
                dir('dist') {
                    deleteDir()
                }
                sshagent([credential_id]) {
                    sh "tools/release.sh --publish ${release_type}"
                }
                currentBuild.description = release
            }
        } catch(e) {
            sshagent([credential_id]) {
                sh "tools/release.sh --cancel ${release_type}"
            }
            currentBuild.result = 'FAILURE'
            throw e
        }
    }
}
