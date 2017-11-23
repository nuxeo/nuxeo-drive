#!groovy
// Script to launch Nuxeo Drive tests on every supported platform.

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
            name: 'SPECIFIC_TEST',
            defaultValue: '',
            description: 'Specific test to launch. The syntax must be the same as <a href="http://doc.pytest.org/en/latest/example/markers.html#selecting-tests-based-on-their-node-id">pytest markers</a>'],
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

                    stage(osi + ' Tests') {
                        // Launch the tests suite
                        if (currentBuild.result == 'UNSTABLE' || currentBuild.result == 'FAILURE') {
                            echo 'Stopping early: apparently another slave did not try its best ...'
                            return
                        }

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
                                        sh "${mvnHome}/bin/mvn -f ftest/pom.xml clean verify -Pqa,pgsql ${platform_opt}"
                                    }
                                } else if (osi == 'GNU/Linux') {
                                    sh "${mvnHome}/bin/mvn -f ftest/pom.xml clean verify -Pqa,pgsql ${platform_opt}"
                                } else {
                                    bat(/"${mvnHome}\bin\mvn" -f ftest\pom.xml clean verify -Pqa,pgsql ${platform_opt}/)
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
