#!groovy
// Script to launch Nuxeo Drive tests on every supported platform.

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
        [$class: 'BooleanParameterDefinition',
            name: 'ENABLE_SONAR',
            defaultValue: true,
            description: 'Run SonarCloud.io analysis.']
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
downstream_jobs = [:]

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

if (env.BRANCH_NAME.startsWith('wip-')) {
    // Do not launch anything if we are on a Work In Progress branch
    skip_tests('WIP')
    return
} else if (env.BRANCH_NAME.startsWith('dependabot')) {
    // Do not launch anything if it is only dependencies upgrade
    skip_tests('DEPS')
    return
}

def checkout_custom() {
    build_changeset = currentBuild.changeSets.isEmpty()
    checkout(
        changelog: build_changeset,
        scm: [$class: 'GitSCM',
        branches: [[name: env.BRANCH_NAME]],
        browser: [$class: 'GithubWeb', repoUrl: repos_url],
        doGenerateSubmoduleConfigurations: false,
        extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'sources']],
        submoduleCfg: [],
        userRemoteConfigs: [[url: repos_git]]])
}

def get_changed_files() {
    // Return a list of strings corresponding to the path of the changed files
    def allFiles = []
    if (env.BUILD_NUMBER == "1" && env.BRANCH_NAME != "master") {
        // On the first build, there is no changelog in currentBuild.changeSets,
        // so we need to figure out the diff from master on our own
        node("SLAVE") {
            checkout_custom()
            dir("sources") {
                sh "git config --add remote.origin.fetch +refs/heads/master:refs/remotes/origin/master"
                sh "git fetch --no-tags"
                allFiles = sh(returnStdout: true, script: "git diff --name-only origin/master..origin/${env.BRANCH_NAME}").split()
            }
        }
        return allFiles
    }

    def changeLogSets = currentBuild.changeSets
    for (changeLog in changeLogSets) {
        for (entry in changeLog.items) {
            for (file in entry.affectedFiles) {
                allFiles.add(file.path)
            }
        }
    }
    return allFiles
}

def has_code_changes() {
    def cause = currentBuild.rawBuild.getCauses()[0].toString()
    if (cause.contains('UserIdCause') || cause.contains("UpstreamCause")) {
        // Build has been triggered manually or by an upstream job, we must run the tests
        return true
    }
    def files = get_changed_files()
    def code_extensions = [".py", ".sh", ".ps1", ".groovy"]
    for (file in files) {
        echo "[+] ${file}"
        for (ext in code_extensions) {
            if (file.trim().endsWith(ext)) {
                // Changes in the code, we must run the tests
                return true
            }
        }
    }
    return false
}

def run_sonar() {
    checkout_custom()

    def jdk = tool name: 'java-11-openjdk'
    env.JAVA_HOME = "${jdk}"
    def mvnHome = tool name: 'maven-3.3', type: 'hudson.tasks.Maven$MavenInstallation'

    dir('sources') {
        def drive_version = sh(
            script: """
                    python -c 'import nxdrive; print(nxdrive.__version__)'; \
                    cd .. \
                    """,
            returnStdout: true).trim()
        echo "Testing Drive ${drive_version}"

        def suffix = (env.BRANCH_NAME == 'master') ? 'master' : 'dynamic'
        for (def label in agents.keySet()) {
            try {
                copyArtifacts(
                    projectName: "../Drive-OS-test-jobs/Drive-tests-${label}-${suffix}",
                    filter: "sources/.coverage", target: "..",
                    selector: specific("${downstream_jobs[label].number}")
                )
                sh "mv .coverage .coverage.${label}"
                echo "Retrieved .coverage.${label}"
            } catch (e) {
                currentBuild.result = 'UNSTABLE'
            }
        }

        sh "./tools/qa.sh"
        archiveArtifacts artifacts: 'htmlcov', fingerprint: true, allowEmptyArchive: true
        archiveArtifacts artifacts: 'coverage.xml', fingerprint: true, allowEmptyArchive: true
        archiveArtifacts artifacts: 'pylint-report.txt', fingerprint: true, allowEmptyArchive: true

        withCredentials([usernamePassword(credentialsId: 'c4ced779-af65-4bce-9551-4e6c0e0dcfe5', passwordVariable: 'SONARCLOUD_PWD', usernameVariable: '')]) {
            withEnv(["WORKSPACE=${pwd()}"]) {
                sh """
                ${mvnHome}/bin/mvn -f ftest/pom.xml sonar:sonar \
                    -Dsonar.login=${SONARCLOUD_PWD} \
                    -Dsonar.branch.name=${env.BRANCH_NAME} \
                    -Dsonar.projectKey=org.nuxeo:nuxeo-drive-client \
                    -Dsonar.projectBaseDir="${env.WORKSPACE}" \
                    -Dsonar.projectVersion="${drive_version}" \
                    -Dsonar.sources=../nxdrive \
                    -Dsonar.tests=../tests \
                    -Dsonar.python.coverage.reportPaths=coverage.xml \
                    -Dsonar.python.pylint.reportPath=pylint-report.txt \
                    -Dsonar.exclusions=ftest/pom.xml
                """
            }
        }
    }
}

stage("Code diff check") {
    if (!has_code_changes()) {
        skip_tests("No code changes")
    }
}

if (currentBuild.result == "ABORTED") {
    // We need a "return" outside of a stage to exit the pipeline
    return
}

def successes = 0

for (def x in agents.keySet()) {
    // Need to bind the label variable before the closure - can't do 'for (agent in agents)'
    def label = x
    def name = names.get(label)

    // Create a map to pass in to the 'parallel' step so we can fire all the builds at once
    builders[label] = {
        stage("Trigger ${name}") {
            // Trigger the job on all OSes
            def suffix = (env.BRANCH_NAME == 'master') ? 'master' : 'dynamic'
            def job_name = "../Drive-OS-test-jobs/Drive-tests-${label}-${suffix}"
            def test_job = build job: job_name, propagate: false, parameters: [
                [$class: 'StringParameterValue', name: 'SPECIFIC_TEST', value: params.SPECIFIC_TEST],
                [$class: 'StringParameterValue', name: 'PYTEST_ADDOPTS', value: params.PYTEST_ADDOPTS],
                [$class: 'StringParameterValue', name: 'RANDOM_BUG_MODE', value: params.RANDOM_BUG_MODE],
                [$class: 'StringParameterValue', name: 'ENGINE', value: params.ENGINE],
                [$class: 'BooleanParameterValue', name: 'CLEAN_WORKSPACE', value: params.CLEAN_WORKSPACE],
                [$class: 'StringParameterValue', name: 'BRANCH_NAME', value: env.BRANCH_NAME]
            ]
            downstream_jobs[label] = test_job
            echo "${name} tests: ${test_job.result}"
            if (test_job.result == "SUCCESS") {
                successes += 1
            }
        }
    }
}

timeout(240) {
    timestamps {
        try {
            parallel builders
        } finally {
            // Update revelant Jira issues only if we are working on the master branch
            if (env.BRANCH_NAME == 'master') {
                node('SLAVE') {
                    step([$class: 'JiraIssueUpdater',
                        issueSelector: [$class: 'DefaultIssueSelector'],
                        scm: scm])
                }
            }
            if (successes == 3) {
                currentBuild.result = "SUCCESS"
            } else if (successes == 0) {
                currentBuild.result = "FAILURE"
            } else {
                currentBuild.result = "UNSTABLE"
            }
        }

        if (env.ENABLE_SONAR && currentBuild.result != "FAILURE" && env.SPECIFIC_TEST == '') {
            node('SLAVE') {
                stage('SonarQube Analysis') {
                    try {
                        run_sonar()
                    } catch(e) {
                        currentBuild.result = 'UNSTABLE'
                        throw e
                    }
                }
            }
        }
    }
}
