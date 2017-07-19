#!groovy
// Script to launch Nuxeo Drive tests on every supported platform.

// Default values for required envars
python_drive_version = '2.7.13'
pyqt_version = '4.12'
cxfreeze_version = '4.3.3'
sip_version = '4.19'

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([[$class: 'TimerTrigger', spec: '@midnight']]),
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false],
    [$class: 'ParametersDefinitionProperty', parameterDefinitions: [
        [$class: 'StringParameterDefinition',
            name: 'SPECIFIC_TEST',
            defaultValue: '',
            description: 'Specific test to launch. The syntax must be the same as <a href="http://doc.pytest.org/en/latest/example/markers.html#selecting-tests-based-on-their-node-id">pytest markers</a>'],
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
        [$class: 'ChoiceParameterDefinition',
            name: 'RANDOM_BUG_MODE',
            choices: 'None\nRELAX\nSTRICT\nBYPASS',
            description: 'Random bug mode'],
        [$class: 'StringParameterDefinition',
            name: 'ENGINE',
            defaultValue: 'NXDRIVE',
            description: '<i>Optional</i> The engine to use (another possible value is <i>NXDRIVENEXT</i>)'],
        [$class: 'BooleanParameterDefinition',
            name: 'CLEAN_WORKSPACE',
            defaultValue: false,
            description: 'Clean the entire workspace before doing anything.'],
        [$class: 'BooleanParameterDefinition',
            name: 'ENABLE_PROFILER',
            defaultValue: false,
            description: 'Use yappi profiler.']
    ]]
])

// Do not launch anything if we are on a Work In Progress branch
if (env.BRANCH_NAME.startsWith('wip-')) {
    echo 'Skipped due to WIP branch.'
    return
}

// Jenkins slaves we will build on
//slaves = ['OSXSLAVE-DRIVE', 'SLAVE810', 'WINSLAVE']
slaves = ['OSXSLAVE-DRIVE', 'WINSLAVE']  // removed GNU/Linux slave as it cannot be updated with required dependencies
labels = [
    'OSXSLAVE-DRIVE': 'macOS',
    'SLAVE810': 'GNU/Linux',
    'WINSLAVE': 'Windows'
]
builders = [:]

// GitHub stuff
repos_url = 'https://github.com/nuxeo/nuxeo-drive'
repos_git = 'https://github.com/nuxeo/nuxeo-drive.git'
status_msg = [
    'FAILURE': 'Failed to build on Nuxeo CI',
    'PENDING': 'Building on on Nuxeo CI',
    'SUCCESS': 'Successfully built on Nuxeo CI'
]

def github_status(status) {
    step([$class: 'GitHubCommitStatusSetter',
        reposSource: [$class: 'ManuallyEnteredRepositorySource', url: repos_url],
        contextSource: [$class: 'ManuallyEnteredCommitContextSource', context: 'ci/qa.nuxeo.com'],
        statusResultSource: [$class: 'ConditionalStatusResultSource',
            results: [[$class: 'AnyBuildResult',
                message: status_msg.get(status), state: status]]]])
}

def checkout_custom() {
    checkout([$class: 'GitSCM',
        branches: [[name: env.BRANCH_NAME]],
        browser: [$class: 'GithubWeb', repoUrl: repos_url],
        doGenerateSubmoduleConfigurations: false,
        extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'sources']],
        submoduleCfg: [],
        userRemoteConfigs: [[url: repos_git]]])
}

for (def x in slaves) {
    // Need to bind the label variable before the closure - can't do 'for (slave in slaves)'
    def slave = x
    def osi = labels.get(slave)

    // Create a map to pass in to the 'parallel' step so we can fire all the builds at once
    builders[slave] = {
        node(slave) {
            withEnv(["WORKSPACE=${pwd()}"]) {
                if (params.CLEAN_WORKSPACE) {
                    deleteDir()
                }

                // Required envars
                env.PYTHON_DRIVE_VERSION = params.PYTHON_DRIVE_VERSION ?: python_drive_version
                env.PYQT_VERSION = params.PYQT_VERSION ?: pyqt_version
                env.DRIVE_YAPPI = params.ENABLE_PROFILER ? env.WORKSPACE : ''

                try {
                    stage(osi + ' Checkout') {
                        try {
                            dir('sources') {
                                deleteDir()
                            }
                            github_status('PENDING')
                            checkout_custom()
                        } catch(e) {
                            currentBuild.result = 'UNSTABLE'
                            throw e
                        }
                    }

                    stage(osi + ' Setup') {
                        // Set up a complete isolated environment
                        try {
                            dir('sources') {
                                if (osi == 'macOS') {
                                    sh 'tools/osx/deploy_jenkins_slave.sh'
                                } else if (osi == 'GNU/Linux') {
                                    sh 'tools/linux/deploy_jenkins_slave.sh'
                                } else {
                                    bat 'powershell ".\\tools\\windows\\deploy_jenkins_slave.ps1"'
                                }
                            }
                        } catch(e) {
                            currentBuild.result = 'UNSTABLE'
                            throw e
                        }
                    }

                    stage(osi + ' Tests') {
                        // Launch the tests suite
                        def jdk = tool name: 'java-8-oracle'
                        env.JAVA_HOME = "${jdk}"
                        def mvnHome = tool name: 'maven-3.3', type: 'hudson.tasks.Maven$MavenInstallation'
                        def platform_opt = "-Dplatform=${slave.toLowerCase()}"

                        dir('sources') {
                            // Set up the report name folder
                            env.REPORT_PATH = env.WORKSPACE + '/sources'
                            env.TEST_REMOTE_SCAN_VOLUME = 100

                            try {
                                if (osi == 'macOS') {
                                    // Adjust the PATH
                                    def env_vars = [
                                        'PATH+LOCALBIN=/usr/local/bin',
                                    ]
                                    withEnv(env_vars) {
                                        sh "${mvnHome}/bin/mvn -f ftest/pom-8.10.xml clean verify -Pqa,pgsql ${platform_opt}"
                                    }
                                } else if (osi == 'GNU/Linux') {
                                    sh "${mvnHome}/bin/mvn -f ftest/pom-8.10.xml clean verify -Pqa,pgsql ${platform_opt}"
                                } else {
                                    bat(/"${mvnHome}\bin\mvn" -f ftest\pom-8.10.xml clean verify -Pqa,pgsql ${platform_opt}/)
                                }
                            } catch(e) {
                                currentBuild.result = 'FAILURE'
                                throw e
                            }
                        }

                        // echo 'Retrieve coverage statistics'
                        // archive 'coverage/*'

                        currentBuild.result = 'SUCCESS'
                    }
                } finally {
                    // We use catchError to not let notifiers and recorders change the current build status
                    catchError {
                        // Update GitHub status whatever the result
                        github_status(currentBuild.result)

                        archive 'sources/ftest/target*/tomcat/log/*.log, sources/*.zip, *yappi.txt'

                        // Update revelant Jira issues only if we are working on the master branch
                        if (env.BRANCH_NAME == 'master') {
                            step([$class: 'JiraIssueUpdater',
                                issueSelector: [$class: 'DefaultIssueSelector'],
                                scm: scm, comment: osi])
                        }
                    }
                }
            }
        }
    }
}

timeout(240) {
    timestamps {
        parallel builders
    }
}
