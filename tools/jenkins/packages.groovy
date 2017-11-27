#!groovy
// Script to build Nuxeo Drive packages on every supported platform.

// Default values for required envars
python_drive_version = '2.7.14'  // XXX: PYTHON_DRIVE_VERSION
pyqt_version = '4.12.1'  // XXX: PYQT_VERSION

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([[$class: 'GitHubPushTrigger']]),
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
// Note 2017-07-21
//      TWANG is the older macOS version we have.
//      Until we change the minimum macOS version from 10.5 to 10.9,
//      we have to keep that slave.
//      Then, OSXSLAVE-DRIVE will be the good value.
// Note 2017-07-21:
//      Later, when we will be in Python3/Qt5, the good value will be OSXSLAVE.
slaves = ['TWANG', 'SLAVE', 'WINSLAVE']
labels = [
    'TWANG': 'macOS',
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
                                sh 'tools/osx/deploy_jenkins_slave.sh --build'
                                archive 'dist/*.dmg, dist/*.zip'
                            } else if (osi == 'GNU/Linux') {
                                sh 'tools/linux/deploy_jenkins_slave.sh --build'
                                archive 'dist/*.json, dist/*.deb, dist/*.zip'
                            } else {
                                bat 'powershell ".\\tools\\windows\\deploy_jenkins_slave.ps1" -build'
                                archive 'dist/*.msi, dist/*.zip'
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

timestamps {
    parallel builders
}
