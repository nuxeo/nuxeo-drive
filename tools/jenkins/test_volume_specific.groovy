#!groovy
// Script to launch volume tests on Nuxeo Drive.

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([[$class: 'GitHubPushTrigger']]),
    [$class: 'BuildDiscarderProperty', strategy:
        [$class: 'LogRotator', daysToKeepStr: '60', numToKeepStr: '60', artifactNumToKeepStr: '5']],
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false],
    parameters([
        string(name: 'BRANCH_NAME', defaultValue: 'master', description: 'The git branch to checkout.', trim: true),
        string(name: 'NXDRIVE_TEST_NUXEO_URL', defaultValue: 'http://localhost:8080/nuxeo', description: 'The server URL against to run tests.', trim: true),
        string(name: 'NXDRIVE_TEST_USERNAME', defaultValue: 'Administrator', description: 'The user having administrator rights.', trim: true),
        string(name: 'NXDRIVE_TEST_PASSWORD', defaultValue: 'Administrator', description: 'The password associated to the username.', trim: true),
        string(name: 'NXDRIVE_TEST_PATH', defaultValue: '/default-domain/workspaces', description: 'The remote path where to store data. Must exist.', trim: true),
        string(name: 'DOCTYPE_FILE', defaultValue: 'File', description: 'Document type for file creations.', trim: true),
        string(name: 'DOCTYPE_FOLDERISH', defaultValue: 'Folder', description: 'Document type for non-file creations.', trim: true),
        string(name: 'TEST_VOLUME', defaultValue: '3,200,3', description: '<ul><li>number of folders</li><li>number of files to create inside each folder</li><li>depth: the tree will be replicated into itself <i>depth</i> times</li><li>Total is <code>...</code> (here 309,858)</ul>', trim: true),
        string(name: 'TEST_REMOTE_SCAN_VOLUME', defaultValue: '200000', description: 'Minimum number of documents to randomly import (here > 200,000).', trim: true),
        booleanParam(name: 'USE_MAC_DRIVE_1', defaultValue: true, description: 'macOS client n° 1.'),
        booleanParam(name: 'USE_MAC_DRIVE_2', defaultValue: false, description: 'macOS client n° 2.'),
        booleanParam(name: 'USE_SLAVE', defaultValue: true, description: 'GNU/Linux client'),
        booleanParam(name: 'USE_WINDB1', defaultValue: true, description: 'Windows client n°1'),
        booleanParam(name: 'USE_WINDB2', defaultValue: false, description: 'Windows client n°2'),
        booleanParam(name: 'USE_WINDB3', defaultValue: false, description: 'Windows client n°3'),
        booleanParam(name: 'USE_WINDB4', defaultValue: false, description: 'Windows client n°4'),
        booleanParam(name: 'USE_WINDB5', defaultValue: false, description: 'Windows client n°5'),
    ])
])

def checkout_custom() {
    // git checkout on a custom branch
    repos_url = 'https://github.com/nuxeo/nuxeo-drive'
    repos_git = 'https://github.com/nuxeo/nuxeo-drive.git'
    checkout([$class: 'GitSCM',
        branches: [[name: params.BRANCH_NAME]],
        browser: [$class: 'GithubWeb', repoUrl: repos_url],
        userRemoteConfigs: [[url: repos_git]]])
}

// Available Jenkins agents
agents = [
    'MAC-DRIVE-1',
    'MAC-DRIVE-2',
    'SLAVE',
    'windb1',
    'windb2',
    'windb3',
    'windb4',
    'windb5',
]
labels = [
    'MAC-DRIVE-1': 'Mac-1',
    'MAC-DRIVE-2': 'Mac-2',
    'SLAVE': 'Linux',
    'windb1': 'Windows-1',
    'windb2': 'Windows-2',
    'windb3': 'Windows-3',
    'windb4': 'Windows-4',
    'windb5': 'Windows-5',
]
builders = [:]

for (x in agents) {
    def agent = x
    def agent_snake_case = agent.replace('-', '_').toUpperCase()
    def osi = labels.get(agent)

    // Check if agent is selected
    if (!params["USE_${agent_snake_case}"]) {
        continue
    }

    builders[agent] = {
        node(agent) {
            stage(osi) {
                // Checkout (not inside a specific stage to have a better view in the job homepage)
                try {
                    checkout_custom()
                } catch(e) {
                    currentBuild.result = 'UNSTABLE'
                    throw e
                }

                // The test
                env.SPECIFIC_TEST = 'old_functional/test_volume.py'
                env.SKIP = 'rerun'
                env.PYTEST_ADDOPTS = '-n0 -x'

                try {
                    if (agent_snake_case.startsWith('MAC')) {
                        // macOS
                        sh 'tools/osx/deploy_ci_agent.sh --install'
                        sh 'tools/osx/deploy_ci_agent.sh --tests'
                    } else if (agent_snake_case.startsWith('WIN')) {
                        // Windows
                        bat 'powershell ".\\tools\\windows\\deploy_ci_agent.ps1" -install'
                        bat 'powershell ".\\tools\\windows\\deploy_ci_agent.ps1" -tests'
                    } else {
                        // GNU/Linux
                        sh 'tools/linux/deploy_ci_agent.sh --install'
                        sh 'tools/linux/deploy_ci_agent.sh --tests'
                    }
                } catch(e) {
                    currentBuild.result = 'FAILURE'
                    throw e
                }
            }
        }
    }
}

timeout(480) {
    parallel builders
}
