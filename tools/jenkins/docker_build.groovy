#!groovy
// Script to build and deploy a new docker image for Nuxeo Drive GNU/Linux binary builds.

// Pipeline properties
properties([
    disableConcurrentBuilds(),
    pipelineTriggers([]),
    [$class: 'BuildDiscarderProperty', strategy:
        [$class: 'LogRotator', daysToKeepStr: '60', numToKeepStr: '60', artifactNumToKeepStr: '1']],
    [$class: 'SchedulerPreference', preferEvenload: true],
    [$class: 'RebuildSettings', autoRebuild: false, rebuildDisabled: false],
    [$class: 'ParametersDefinitionProperty', parameterDefinitions: [
        [$class: 'StringParameterDefinition',
            name: 'PYTHON_VERSION',
            defaultValue: 'x.y.z',
            description: 'The Python version in-use for the current Nuxeo Drive version.']
    ]]
])

// Do not allow to rebuild past images
def protected_versions = [
    'x.y.z'  // ,'3.7.4'
]
if (protected_versions.contains(params.PYTHON_VERSION)) {
    def reason = "${params.PYTHON_VERSION} already exists!"
    if (params.PYTHON_VERSION == 'x.y.z') {
        reason = "No Python version."
    }
    echo reason
    currentBuild.description = reason
    currentBuild.result = "ABORTED"
    return
}

node('IT') {
    stage('Build') {
        def scmvars = checkout(scm)

        docker.withRegistry('https://dockerpriv.nuxeo.com/') {
            def image = docker.build(
                "nuxeo-drive-build:py-${params.PYTHON_VERSION}",
                "--build-arg VERSION=${env.BUILD_NUMBER} --build-arg SCM_REF=${scmvars.GIT_COMMIT} tools/linux")
            image.push()
        }

        currentBuild.description = "nuxeo-drive-build:py-${params.PYTHON_VERSION}"
    }
}
