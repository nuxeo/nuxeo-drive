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
            name: 'BYPASS_ACCOUNT',
            defaultValue: true,
            description: 'Used by the auto-updater to bypass the need for an account.'],
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
                currentBuild.description = params.BRANCH_NAME

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

                stage(osi) {
                    // First step, curcial, will check the auto-update process.
                    // It is a quality of service to prevent releasing a bad version.
                    // Then installers and bianires are built.

                    // Note: there seems to be too many commands that could have been split into sub-stages,
                    //       but this would duplicate too many things and take too much time and resources.

                    env.FORCE_USE_LATEST_VERSION = env.BYPASS_ACCOUNT ? 1 : 0

                    dir('sources') {
                        dir('build') {
                            deleteDir()
                        }
                        dir('dist') {
                            deleteDir()
                        }

                        try
                        {
                            if (osi == 'GNU/Linux')
                            {
                                // No auto-update check on GNU/Linux as AppImage cannot be started from our headless agents, sadly.
                                // But this is not a big deal as the auto-update process on GNU/Linux is really a simple copy.

                                // Build the binary
                                docker.withRegistry('https://dockerpriv.nuxeo.com/')
                                {
                                    def image = docker.image('nuxeo-drive-build:py-3.7.4')  // XXX_PYTHON
                                    image.inside() { sh "/entrypoint.sh" }
                                }

                                // Check the resulting binary is OK
                                sh 'tools/linux/deploy_jenkins_slave.sh --check'

                                // And archive it
                                archiveArtifacts artifacts: 'dist/*.AppImage', fingerprint: true
                            }
                            else if (osi == 'macOS')
                            {
                                def env_vars = [
                                    'SIGNING_ID=NUXEO CORP',
                                    "KEYCHAIN_PATH=${env.HOME}/Library/Keychains/login.keychain-db",
                                ]
                                withEnv(env_vars)
                                {
                                    withCredentials([string(credentialsId: 'MOBILE_LOGIN_KEYCHAIN_PASSWORD',
                                                            variable: 'KEYCHAIN_PASSWORD')]) {
                                        // Install requirements
                                        sh 'tools/osx/deploy_jenkins_slave.sh --install-release'

                                        // Auto-update check
                                        sh 'tools/osx/deploy_jenkins_slave.sh --check-upgrade'

                                        // Build the installer
                                        sh 'tools/osx/deploy_jenkins_slave.sh --build'

                                        // And archive it
                                        archiveArtifacts artifacts: 'dist/*.dmg', fingerprint: true

                                        // Also archive the notarization report
                                        archiveArtifacts artifacts: 'report-*.json', fingerprint: true, allowEmptyArchive: true
                                    }
                                }
                            }
                            else if (osi == 'Windows')
                            {
                                def env_vars = [
                                    'SIGNING_ID=Nuxeo',
                                    'SIGNTOOL_PATH=C:\\Program Files (x86)\\Windows Kits\\10\\App Certification Kit',
                                ]
                                withEnv(env_vars)
                                {
                                    // Install requirements
                                    bat 'powershell ".\\tools\\windows\\deploy_jenkins_slave.ps1" -install_release'

                                    // Auto-update check
                                    bat 'powershell ".\\tools\\windows\\deploy_jenkins_slave.ps1" -check_upgrade'

                                    // Build the installer
                                    bat 'powershell ".\\tools\\windows\\deploy_jenkins_slave.ps1" -build'

                                    // And archive it
                                    archiveArtifacts artifacts: 'dist/*.exe', fingerprint: true
                                }
                            }

                            // Archive ZIP'ed sources
                            archiveArtifacts artifacts: 'dist/*.zip', fingerprint: true
                        }
                        catch(e)
                        {
                            currentBuild.result = 'FAILURE'
                            throw e
                        }
                        finally {
                            // Retrieve auto-update logs when possible
                            archiveArtifacts artifacts: 'nxdrive-*.log', fingerprint: true, allowEmptyArchive: true
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
