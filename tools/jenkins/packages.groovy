#!groovy
// Script to build Nuxeo Drive packages on every supported platform.

// Default values for required envars
python_drive_version = '2.7.13'  // XXX: PYTHON_DRIVE_VERSION
pyqt_version = '4.12.1'  // XXX: PYQT_VERSION
sip_version = '4.19.3'  // XXX: SIP_VERSION
cxfreeze_version = '4.3.3'  // XXX: CXFREEZE_VERSION

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
        [$class: 'StringParameterDefinition',
            name: 'PYTHON_DRIVE_VERSION',
            defaultValue: python_drive_version,
            description: '<b>Required</b> Python version to use'],
        [$class: 'StringParameterDefinition',
            name: 'PYQT_VERSION',
            defaultValue: pyqt_version,
            description: '<b>Required</b> PyQt version to use (GNU/Linux and macOS only)'],
        [$class: 'StringParameterDefinition',
            name: 'CXFREEZE_VERSION',
            defaultValue: cxfreeze_version,
            description: '<i>Optional</i> cx_Freeze version to use'],
        [$class: 'StringParameterDefinition',
            name: 'SIP_VERSION',
            defaultValue: sip_version,
            description: '<i>Optional</i> SIP version to use (GNU/Linux and macOS only)'],
        [$class: 'StringParameterDefinition',
            name: 'ENGINE',
            defaultValue: 'NXDRIVE',
            description: '<i>Optional</i> The engine to use (another possible value is <i>NXDRIVENEXT</i>)'],
        [$class: 'BooleanParameterDefinition',
            name: 'CLEAN_WORKSPACE',
            defaultValue: false,
            description: 'Clean the entire workspace before doing anything.']
    ]]
])

// Jenkins slaves we will build on
slaves = ['OSXSLAVE', 'SLAVE', 'WINSLAVE']
labels = [
    'OSXSLAVE': 'macOS',
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
                        currentBuild.description = "Python ${params.PYTHON_DRIVE_VERSION}, Qt ${params.PYQT_VERSION}<br/>${params.BRANCH_NAME}"
                    }
                }
            }
        }
    }
}

timestamps {
    parallel builders
}
