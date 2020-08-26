#!groovy
// Script to launch volume tests on Nuxeo Drive.

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
            name: 'TEST_VOLUME',
            defaultValue: '6,1200,3',
            description: '<ul><li>number of folders</li><li>number of files to create inside each folder</li><li>depth: the tree will be replicated into itself <i>depth</i> times</li><li>Total is <code>...</code> (here 309,858)</ul>'],
        [$class: 'StringParameterDefinition',
            name: 'TEST_REMOTE_SCAN_VOLUME',
            defaultValue: '200000',
            description: 'Minimum number of documents to randomly import (here > 200,000).']
    ]]
])

// Jenkins agents we will build on
agents = ['SLAVE', 'OSXSLAVE-DRIVE', 'WINSLAVE']
labels = [
    'SLAVE': 'GNU/Linux',
    'OSXSLAVE-DRIVE': 'macOS',
    'WINSLAVE': 'Windows'
]
builders = [:]

for (x in agents) {
    def agent = x
    def osi = labels.get(agent)

    builders[agent] = {
        node(agent) {
            stage(osi + ' Checkout') {
                try {
                    checkout(scm)
                } catch(e) {
                    currentBuild.result = 'UNSTABLE'
                    throw e
                }
            }

            stage(osi + ' Test') {
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

                // Set up the report name folder
                env.REPORT_PATH = env.WORKSPACE

                // The test
                env.SPECIFIC_TEST = 'old_functional/test_volume.py'
                env.SKIP = 'rerun'
                env.PYTEST_ADDOPTS = '-n0 -x'

                try {
                    if (osi == 'GNU/Linux') {
                        sh "${mvnHome}/bin/mvn -f ftest/pom.xml clean verify -Pqa,pgsql ${platform_opt}"
                    } else if (osi == 'macOS') {
                        // Adjust the PATH
                        def env_vars = [
                            'PATH+LOCALBIN=/usr/local/bin',
                            'PATH+SBIN=/usr/sbin',
                        ]
                        withEnv(env_vars) {
                            sh "mvn -f ftest/pom.xml clean verify -Pqa,pgsql ${platform_opt}"
                        }
                    } else {
                        bat(/"${mvnHome}\bin\mvn" -f ftest\pom.xml clean verify -Pqa,pgsql ${platform_opt}/)
                    }
                } catch(e) {
                    currentBuild.result = 'FAILURE'
                    throw e
                } finally {
                    archiveArtifacts artifacts: 'ftest/target*/tomcat/log/*.log, *.zip, *yappi.txt, .coverage, tools/jenkins/junit/xml/**.xml', fingerprint: true, allowEmptyArchive: true
                }
            }
        }
    }
}

timeout(480) {
    parallel builders
}
