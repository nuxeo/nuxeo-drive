#!groovy
// Script to launch Nuxeo Drive tests on every supported platform.

// Pipeline properties
properties([
    [$class: 'BuildDiscarderProperty', strategy:
        [$class: 'LogRotator', daysToKeepStr: '60', numToKeepStr: '60', artifactNumToKeepStr: '1']],
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false],
    [$class: 'ParametersDefinitionProperty', parameterDefinitions: [
        [$class: 'StringParameterDefinition',
            name: 'SPECIFIC_TEST',
            defaultValue: '',
            description: 'Specific test to launch. The syntax must be the same as <a href="http://doc.pytest.org/en/latest/example/markers.html#selecting-tests-based-on-their-node-id">pytest markers</a>. We have those folders:<ul><li>Unit tests: <code>unit</code></li><li>Functional tests: <code>functional</code></li><li>Old functional tests: <code>old_functional</code></li><li>Integration tests: <code>integration</code></li></ul>Examples:<ul><li>All tests from a file: <code>units/test_utils.py</code></li><li>Test a single function: <code>functional/test_updater.py::test_get_update_status</code></li><li>All tests from a class: <code>old_functional/test_watchers.py::TestWatchers</code></li><li>Test a single method: <code>old_functional/test_watchers.py::TestWatchers::test_local_scan_error</code></li></ul>'],
        [$class: 'StringParameterDefinition',
            name: 'PYTEST_ADDOPTS',
            defaultValue: '-n4',
            description: 'Extra command line options for pytest. They override any previsously set options. Examples:<ul><li>Number of cores to use: <code>-n X</code> ("auto" to enable all, default)</li><li>Useful for debugging: <code>--capture=no</code></li></ul>'],
        [$class: 'ChoiceParameterDefinition',
            name: 'RANDOM_BUG_MODE',
            choices: 'None\nRELAX\nSTRICT\nBYPASS',
            description: 'Random bug mode'],
        [$class: 'StringParameterDefinition',
            name: 'ENGINE',
            defaultValue: 'NXDRIVE',
            description: 'The engine to use.'],
        [$class: 'BooleanParameterDefinition',
            name: 'CLEAN_WORKSPACE',
            defaultValue: false,
            description: 'Clean the entire workspace before doing anything.'],
        [$class: 'StringParameterDefinition',
            name: 'BRANCH_NAME',
            defaultValue: 'master',
            description: 'The branch to checkout.']
    ]]
])

// Jenkins agents we will build on
agents = [
    'macos': 'OSXSLAVE-DRIVE',
    'linux': 'SLAVE',
    'windows': 'WINSLAVE'
]
names = [
    'macos': 'macOS',
    'linux': 'GNU/Linux',
    'windows': 'Windows'
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

def skip_tests(reason) {
    echo reason
    currentBuild.description = "Skipped: ${reason}"
    currentBuild.result = "ABORTED"
}

// Do not launch anything if we are on a Work In Progress branch
if (params.BRANCH_NAME.startsWith('wip-')) {
    skip_tests('WIP')
    return
}

def github_status(status) {
    step([$class: 'GitHubCommitStatusSetter',
        reposSource: [$class: 'ManuallyEnteredRepositorySource', url: repos_url],
        contextSource: [$class: 'ManuallyEnteredCommitContextSource', context: 'ci/qa.nuxeo.com'],
        statusResultSource: [$class: 'ConditionalStatusResultSource',
            results: [[$class: 'AnyBuildResult',
                message: status_msg.get(status), state: status]]]])
}

def checkout_custom() {
    build_changeset = currentBuild.changeSets.isEmpty()
    checkout(
        changelog: build_changeset,
        scm: [$class: 'GitSCM',
        branches: [[name: params.BRANCH_NAME]],
        browser: [$class: 'GithubWeb', repoUrl: repos_url],
        doGenerateSubmoduleConfigurations: false,
        extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'sources']],
        submoduleCfg: [],
        userRemoteConfigs: [[url: repos_git]]])
}

if (currentBuild.result == "ABORTED") {
    // We need a "return" outside of a stage to exit the pipeline
    return
}

// We have a specific operating system
def label = (env.JOB_NAME =~ /Drive-tests-(\w+)-\w+/)[0][1]
def agent = agents.get(label)
def osi = names.get(label)

node(agent) {
    timeout(240) {
        withEnv(["WORKSPACE=${pwd()}"]) {
            // TODO: Remove the Windows part when https://github.com/pypa/pip/issues/3055 is resolved
            if (params.CLEAN_WORKSPACE || osi == "Windows") {
                deleteDir()
            }

            try {
                stage("${osi} Checkout") {
                    try {
                        dir('sources') {
                            deleteDir()
                        }
                        //github_status('PENDING')
                        checkout_custom()
                    } catch(e) {
                        currentBuild.result = 'UNSTABLE'
                        throw e
                    }
                }

                stage("${osi} Tests") {
                    // Launch the tests suite

                    def jdk = tool name: 'java-11-openjdk'
                    env.JAVA_HOME = "${jdk}"
                    def mvnHome = tool name: 'maven-3.3', type: 'hudson.tasks.Maven$MavenInstallation'
                    def platform_opt = "-Dplatform=${agent.toLowerCase()}"

                    // This is a dirty hack to bypass PGSQL errors, see NXDRIVE-1370 for more information.
                    // We cannot unset hardcoded envars but we can generate a random string ourselves.
                    // Note: that string must start with a letter.
                    def uid = "rand" + UUID.randomUUID().toString().replace('-', '')
                    env.NX_DB_NAME = uid
                    env.NX_DB_USER = uid
                    echo "Using a random string for the database name and user: ${uid}"

                    dir('sources') {
                        // Set up the report name folder
                        env.REPORT_PATH = env.WORKSPACE + '/sources'

                        try {
                            if (osi == 'macOS') {
                                // Adjust the PATH
                                def env_vars = [
                                    'PATH+LOCALBIN=/usr/local/bin',
                                    'PATH+SBIN=/usr/sbin',
                                ]
                                withEnv(env_vars) {
                                    sh "mvn -B -f ftest/pom.xml clean verify -Pqa,pgsql ${platform_opt}"
                                }
                            } else if (osi == 'GNU/Linux') {
                                sh "${mvnHome}/bin/mvn -B -f ftest/pom.xml clean verify -Pqa,pgsql ${platform_opt}"
                            } else {
                                bat(/"${mvnHome}\bin\mvn" -B -f ftest\pom.xml clean verify -Pqa,pgsql ${platform_opt}/)
                            }
                        } catch(e) {
                            currentBuild.result = 'FAILURE'
                            throw e
                        }
                    }
                    currentBuild.result = 'SUCCESS'
                }
            } finally {
                // We use catchError to not let notifiers and recorders change the current build status
                catchError(buildResult: null, message: "Error during archiving", stageResult: null) {
                    // Update GitHub status whatever the result
                    //github_status(currentBuild.result)

                    junit 'sources/tools/jenkins/junit/xml/junit.xml'
                    archiveArtifacts artifacts: 'sources/ftest/target*/tomcat/log/*.log, sources/*.zip, *yappi.txt, sources/.coverage, sources/tools/jenkins/junit/xml/**.xml', fingerprint: true, allowEmptyArchive: true
                }
            }
        }
    }
}
