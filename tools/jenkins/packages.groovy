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
agents = ['SLAVEPRIV', 'OSXSLAVE-DRIVE', 'WINSLAVE']
labels = [
    'SLAVEPRIV': 'GNU/Linux',
    'OSXSLAVE-DRIVE': 'macOS',
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
                                def branch = params.BRANCH_NAME
                                // Handle alpha branches
                                if (branch.contains('refs/tags/')) {
                                    branch = branch.replace('refs/tags/', 'wip-')
                                }

                                docker.withRegistry('https://dockerpriv.nuxeo.com/') {
                                    def image = docker.image('nuxeo-drive-build:py-3.7.4')  // XXX_PYTHON
                                    image.inside() { sh "/entrypoint.sh" }
                                }
                                sh 'tools/linux/deploy_jenkins_slave.sh --check'
                                archiveArtifacts artifacts: 'dist/*.AppImage', fingerprint: true
                            } else if (osi == 'macOS') {
                                def env_vars = [
                                    'SIGNING_ID=NUXEO CORP',
                                    'KEYCHAIN_PATH=/Users/jenkins/Library/Keychains/login.keychain-db',
                                ]
                                withEnv(env_vars) {
                                    withCredentials([string(credentialsId: 'MOBILE_LOGIN_KEYCHAIN_PASSWORD',
                                                            variable: 'KEYCHAIN_PASSWORD')]) {
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
