#!groovy
// Script to build Nuxeo Drive packages on every supported platform.

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([[$class: 'GitHubPushTrigger']]),
    [$class: 'BuildDiscarderProperty', strategy:
        [$class: 'LogRotator', daysToKeepStr: '60', numToKeepStr: '60', artifactNumToKeepStr: '1']],
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false],
    [$class: 'ParametersDefinitionProperty', parameterDefinitions: [
        [$class: 'StringParameterDefinition',
            name: 'BRANCH_NAME',
            defaultValue: 'master'],
        [$class: 'BooleanParameterDefinition',
            name: 'CLEAN_WORKSPACE',
            defaultValue: false,
            description: 'Clean the entire workspace before doing anything.']
    ]]
])

// Jenkins agents we will build on
//   We are using TWANG because it is the oldest macOS version we support (10.11).
//   The macOS installer needs to be built on that version to support 10.11+ because
//   PyInstaller is not retro-compatible: if we would build on 10.13, the minimum
//   supported macOS version would become 10.13.
//
agents = ['SLAVEPRIV', 'TWANG', 'WINSLAVE']
labels = [
    'SLAVEPRIV': 'GNU/Linux',
    'TWANG': 'macOS',
    'WINSLAVE': 'Windows'
]
builders = [:]

// GitHub stuff
repos_url = 'https://github.com/nuxeo/nuxeo-drive'
repos_git = 'https://github.com/nuxeo/nuxeo-drive.git'

def checkout_custom() {
    checkout([$class: 'GitSCM',
        branches: [[name: env.BRANCH_NAME]],
        browser: [$class: 'GithubWeb', repoUrl: repos_url],
        doGenerateSubmoduleConfigurations: false,
        extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'sources']],
        submoduleCfg: [],
        userRemoteConfigs: [[url: repos_git]]])
}

for (x in agents) {
    def agent = x
    def osi = labels.get(agent)

    builders[agent] = {
        node(agent) {
            withEnv(["WORKSPACE=${pwd()}"]) {
                if (params.CLEAN_WORKSPACE) {
                    dir('deploy-dir') {
                        deleteDir()
                    }
                }

                stage(osi + ' Checkout') {
                    dir('sources') {
                        deleteDir()
                    }
                    try {
                        checkout_custom()
                    } catch(e) {
                        currentBuild.result = 'UNSTABLE'
                        throw e
                    }
                }

                stage(osi + ' Build') {
                    dir('sources') {
                        dir('build') {
                            deleteDir()
                        }
                        dir('dist') {
                            deleteDir()
                        }

                        try {
                            if (osi == 'GNU/Linux') {
                                docker.withRegistry('https://dockerpriv.nuxeo.com/') {
                                    sh 'mkdir -v dist'
                                    sh 'pwd'
                                    sh "ls -l ${env.WORKSPACE}/sources/dist"
                                    sh "docker run --rm -v ${env.WORKSPACE}/sources/dist:/opt/dist -e 'BRANCH_NAME=${env.BRANCH_NAME}' nuxeo-drive-build:py-3.7.4"  // XXX_PYTHON
                                    sh 'ls -l dist'
                                    sh 'tools/linux/deploy_jenkins_slave.sh --check'
                                    archiveArtifacts artifacts: 'dist/*.AppImage', fingerprint: true
                                }
                            } else if (osi == 'macOS') {
                                // Trigger the Drive extensions job to build extensions and have artifacts
                                build job: 'Drive-extensions', parameters: [
                                    [$class: 'StringParameterValue',
                                        name: 'BRANCH_NAME',
                                        value: params.BRANCH_NAME]]
                                step([$class: 'CopyArtifact', filter: 'extension.zip', projectName: 'Drive-extensions'])

                                def env_vars = [
                                    'SIGNING_ID=NUXEO CORP',
                                    "LOGIN_KEYCHAIN_PATH=${env.HOME}/Library/Keychains/login.keychain",
                                ]
                                withEnv(env_vars) {
                                    withCredentials([string(credentialsId: 'MOBILE_LOGIN_KEYCHAIN_PASSWORD',
                                                            variable: 'LOGIN_KEYCHAIN_PASSWORD')]) {
                                        sh 'tools/osx/deploy_jenkins_slave.sh --install-release'
                                        sh 'tools/osx/deploy_jenkins_slave.sh --build'
                                        archiveArtifacts artifacts: 'dist/*.dmg', fingerprint: true
                                    }
                                }
                            } else {
                                def env_vars = [
                                    'SIGNING_ID=Nuxeo',
                                    'SIGNTOOL_PATH=C:\\Program Files (x86)\\Windows Kits\\10\\App Certification Kit',
                                ]
                                withEnv(env_vars) {
                                    bat 'powershell ".\\tools\\windows\\deploy_jenkins_slave.ps1" -install_release'
                                    bat 'powershell ".\\tools\\windows\\deploy_jenkins_slave.ps1" -build'
                                    archiveArtifacts artifacts: 'dist/*.exe', fingerprint: true
                                }
                            }
                            archiveArtifacts artifacts: 'dist/*.zip', fingerprint: true
                        } catch(e) {
                            currentBuild.result = 'FAILURE'
                            throw e
                        } finally {
                            currentBuild.description = params.BRANCH_NAME
                        }
                    }
                }
            }
        }
    }
}

timeout(120) {
    parallel builders
}
