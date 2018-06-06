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

// Jenkins slaves we will build on
//
//   Until NXDRIVE-351 is done, the SLAVE slave is not needed.
//
//   We are using TWANG because it is the oldest macOS version we support (10.11).
//   The macOS installer needs to be built on that version to support 10.11+ because
//   PyInstaller is not retro-compatible: if we would build on 10.13, the minimum
//   supported macOS version would become 10.13.
//
slaves = ['TWANG', 'WINSLAVE']
labels = [
    'SLAVE': 'GNU/Linux',
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

for (x in slaves) {
    def slave = x
    def osi = labels.get(slave)

    builders[slave] = {
        node(slave) {
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

                stage(osi + ' Extension') {
                    // Trigger the Drive extensions job to build extensions and have artifacts
                    if (osi == 'macOS') {
                        build job: 'Drive-extensions', parameters: [
                            [$class: 'StringParameterValue',
                                name: 'BRANCH_NAME',
                                value: params.BRANCH_NAME]]

                        dir('sources') {
                            step([$class: 'CopyArtifact', filter: 'extension.zip', projectName: 'Drive-extensions'])
                        }
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
                            env.PYTHON_DRIVE_VERSION = '3.7.0'

                            if (osi == 'GNU/Linux') {
                                sh 'tools/linux/deploy_jenkins_slave.sh --build'
                                archive 'dist/*.deb'
                            } else if (osi == 'macOS') {
                                def env_vars = [
                                    'SIGNING_ID=NUXEO CORP',
                                    "LOGIN_KEYCHAIN_PATH=${env.HOME}/Library/Keychains/login.keychain",
                                ]
                                withEnv(env_vars) {
                                    withCredentials([string(credentialsId: 'MOBILE_LOGIN_KEYCHAIN_PASSWORD',
                                                            variable: 'LOGIN_KEYCHAIN_PASSWORD')]) {
                                        sh 'tools/osx/deploy_jenkins_slave.sh --build'
                                        archive 'dist/*.dmg'
                                    }
                                }
                            } else {
                                def env_vars = [
                                    'SIGNING_ID=Nuxeo',
                                    'SIGNTOOL_PATH=C:\\Program Files (x86)\\Windows Kits\\10\\App Certification Kit',
                                ]
                                withEnv(env_vars) {
                                    bat 'powershell ".\\tools\\windows\\deploy_jenkins_slave.ps1" -build'
                                    archive 'dist/*.exe'
                                }
                            }
                        } catch(e) {
                            currentBuild.result = 'FAILURE'
                            throw e
                        } finally {
                            currentBuild.description = "Python ${python_drive_version}, Qt ${pyqt_version}<br/>${params.BRANCH_NAME}"
                        }
                    }
                }
            }
        }
    }
}

timeout(120) {
    timestamps {
        parallel builders
    }
}
