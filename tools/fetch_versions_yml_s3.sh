#!/bin/bash

# Fetch versions.yml
git_env=$1
if [ "$git_env" = "development" ]; then
	url="https://hyland-software-channel-dist.opsexp.alfresco.me/alfresco/drive-updates/versions.yml"
	bucket="s3://test-hyland-software-channel-dist/alfresco/drive-updates/"
elif [ "$git_env" = "production" ]; then
	url="https://drive.software-channels.hyland.com/alfresco/drive-updates/versions.yml"
	bucket="s3://drive.software-channels.hyland.com/alfresco/drive-updates/"
else
	echo "Missing/Incorrect environment provided!! Aborting..."
	exit 1
fi

response=$(curl -l $url)


if [[ $response == *"<Code>AccessDenied</Code>"* ]]; then
	echo "versions.yml not found"
	echo "Creating empty versions.yml file as it does not exist in S3."
	touch versions.yml
    aws s3 cp versions.yml $bucket
	exit 0
else
	echo "versions.yml found !! Downloading...."
	curl -o ./versions.yml $url
	exit 0
fi
