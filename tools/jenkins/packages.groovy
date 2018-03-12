#!groovy
// Script to build Nuxeo Drive packages on every supported platform.

// Default values for required envars
python_drive_version = '2.7.14'  // XXX: PYTHON_DRIVE_VERSION
pyqt_version = '4.12.1'  // XXX: PYQT_VERSION

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
// We need to use OSXSLAVE-DRIVE instead of OSXSLAVE because it contains
// the manual installation of Qt4 & the macOS codesigning certificates.
slaves = ['OSXSLAVE-DRIVE', 'SLAVE', 'WINSLAVE']
labels = [
    'OSXSLAVE-DRIVE': 'macOS',
    'SLAVE': 'GNU/Linux',
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

                stage(osi + ' Build') {
                    dir('sources') {
                        dir('build') {
                            deleteDir()
                        }
                        dir('dist') {
                            deleteDir()
                        }

                        // Required envars
                        env.PYTHON_DRIVE_VERSION = python_drive_version
                        env.PYQT_VERSION = pyqt_version

                        try {
                            if (osi == 'macOS') {
                                env.SIGNING_ID = "NUXEO CORP"
                                env.LOGIN_KEYCHAIN_PATH = "/Users/jenkins/Library/Keychains/login.keychain-db"

                                withCredentials([string(credentialsId: 'MOBILE_LOGIN_KEYCHAIN_PASSWORD', variable: 'LOGIN_KEYCHAIN_PASSWORD')]) {
                                    sh 'tools/osx/deploy_jenkins_slave.sh --build'
                                }
                                archive 'dist/*.dmg'
                            } else if (osi == 'GNU/Linux') {
                                sh 'tools/linux/deploy_jenkins_slave.sh --build'
                                archive 'dist/*.json, dist/*.deb'
                            } else {
                                bat 'powershell ".\\tools\\windows\\deploy_jenkins_slave.ps1" -build'
                                archive 'dist/*.exe, dist/*.msi'
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
