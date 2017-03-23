#!groovy
// Nightly build
// Script to build Nuxeo Drive on every supportable platform.

// Default values for required envars
PYTHON_DRIVE_VERSION = '2.7.13'
PYQT_VERSION = '4.12'
CXFREEZE_VERSION = '4.3.3'
SIP_VERSION = '4.19'

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    overrideIndexTriggers(true),
    pipelineTriggers([[$class: 'TimerTrigger', spec: 'H H(22-23) * * *']]),
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false],
    [$class: 'ParametersDefinitionProperty', parameterDefinitions: [
        [$class: 'StringParameterDefinition',
            name: 'BRANCH_NAME',
            defaultValue: 'master'],
        [$class: 'StringParameterDefinition',
            name: 'PYTHON_DRIVE_VERSION',
            defaultValue: PYTHON_DRIVE_VERSION,
            description: '<b>Required</b> Python version to use'],
        [$class: 'StringParameterDefinition',
            name: 'PYQT_VERSION',
            defaultValue: PYQT_VERSION,
            description: '<b>Required</b> PyQt version to use (GNU/Linux and macOS only)'],
        [$class: 'StringParameterDefinition',
            name: 'CXFREEZE_VERSION',
            defaultValue: CXFREEZE_VERSION,
            description: '<i>Optional</i> cx_Freeze version to use'],
        [$class: 'StringParameterDefinition',
            name: 'SIP_VERSION',
            defaultValue: SIP_VERSION,
            description: '<i>Optional</i> SIP version to use (GNU/Linux and macOS only)'],
        [$class: 'StringParameterDefinition',
            name: 'ENGINE',
            defaultValue: 'NXDRIVE',
            description: '<i>Optional</i> The engine to use (another possible value is <i>NXDRIVENEXT</i>)']
    ]]
])

// Jenkins slaves we will build on
slaves = ['OSXSLAVE', 'SLAVE', 'WINSLAVE']
labels = [
    OSXSLAVE: 'macOS',
    SLAVE: 'GNU/Linux',
    WINSLAVE: 'Windows'
]
builders = [:]

// GitHub stuff
repos_url = 'https://github.com/nuxeo/nuxeo-drive'
repos_git = 'https://github.com/nuxeo/nuxeo-drive.git'

def checkout_custom() {
    checkout([$class: 'GitSCM',
        branches: [[name: '*/' + env.BRANCH_NAME]],
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
                stage(osi + ' Checkout') {
                    checkout_custom()
                }

                stage(osi + ' Build') {
                    dir('sources') {
                        dir('build') {
                            deleteDir()
                        }
                        dir('dist') {
                            deleteDir()
                        }

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
                    }
                }
            }
        }
    }
}

timestamps {
    parallel builders
}
