# Amazon S3 Direct Uploads

- Created: 2019-11-18
- Last-Modified: 2020-01-13
- Author: Mickaël Schoentgen <mschoentgen@nuxeo.com>
- Reviewer: Yannis Achour <yachour@nuxeo.com>,
            Antoine Taillefer <ataillefer@nuxeo.com>
- Status: implemented
- Related-Ticket: [NXDRIVE-1621](https://jira.nuxeo.com/browse/NXDRIVE-1621),
                  [NXDRIVE-1918](https://jira.nuxeo.com/browse/NXDRIVE-1918),
                  [NXPY-138](https://jira.nuxeo.com/browse/NXPY-138),
                  [NXPY-149](https://jira.nuxeo.com/browse/NXPY-149)

## Abstract

Use Amazon S3 for uploads.

## Rationale

The current behavior is to use the default Nuxeo provider, which is the server itself.
Given that S3 is configured on the server, when uploading a blob, it will then do the transfer to S3.
This is very unoptimized because this will ask the server to do a lot of work for each and every upload.

### Idea

The idea is to bypass the need for the server to do the transfer for us.
Nuxeo Drive should upload directly to S3 and tell the server the bucket where the file is stored.
It will ease on the server load and should provide better transfer speed.

It is required to not lose the pause/resume feature for such uploads.

## Specifications

### Amazon S3

There are 2 types of uploads: [single and multipart](https://docs.aws.amazon.com/AmazonS3/latest/dev/UploadingObjects.html).

- Single uploads are using a simple PUT operation and are the best fit for small files.
  The theoric maximum file size is 5 GiB, but Amazon [recommends](https://docs.aws.amazon.com/AmazonS3/latest/dev/uploadobjusingmpu.html) to not go higher than 100 MiB.
  However, given the network stability and bandwidth limitations we cannot know in advance for our users, that value will be lowered to 20 MiB (the current value of the [chunk_limit](https://github.com/nuxeo/nuxeo-drive/blob/bfd8faf/nxdrive/options.py#L196) option).
- Multipart uploads can be used for files bigger than 5 MiB, and up-to 160 TiB.
  They are the way to go for big files as it allows transfer pause/resume.

### Technical Overview

> Note that below statements work thanks to the patched Python client that now supports the S3 upload provider, see [NXPY-138](https://jira.nuxeo.com/browse/NXPY-138) for details.

The [technical overview](https://doc.nuxeo.com/nxdoc/amazon-s3-direct-upload/#technical-overview) document from Nuxeo is a good start to understand what actions are needed in order to use S3.

In short:

1. A client asks for a `Batch` using the `s3` provider.
   The answer contains additional data such as AWS credentials, bucket and key.
2. Using that data, the client can now talk directly to S3 using [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) (the Amazon S3 SDK for Python).
3. When the upload is finished, the client has to tell the server the upload is complete. That step requires to know the ETag set by S3 at the previous step.

For the next sections, let's imagine we already have a Batch, AWS credentials, and the `s3_client` has been created:

```python
import boto3
from nuxeo.client import Nuxeo


# Instantiate the Nuxeo client
nuxeo = Nuxeo(...)

# This is the document that needs a blob
new_file = Document(
    name="File.mkv",
    type="File",
    properties={"dc:title": "File.mkv"},
)
path = "/default-domain/UserWorkspaces/<USER>/Tests S3"
file = nuxeo.documents.create(new_file, parent_path=path)

# The batch to process the blob upload
batch = nuxeo.uploads.batch(handler="s3")

# Instantiate the S3 client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=batch.extraInfo["awsSecretKeyId"],
    aws_secret_access_key=batch.extraInfo["awsSecretAccessKey"],
    aws_session_token=batch.extraInfo["awsSessionToken"],
    region_name=batch.extraInfo["region"],
)
```

### Single Uploads

The [put_object()](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html) method will be used for files smaller than 20 MiB. Its usage is really simple:

```python
# Note: we are using put_object() rather than upload_fileobj()
# to be able to retrieve the ETag from the response. The latter
# returns nothing and it would involve doing another HTTP call
# just to get that information.
with open("<FILE>", "rb") as fd:
    response = s3_client.put_object(
        Bucket="<BUCKET>",
        Key="<KEY>/<FILENAME>",
        Body=fd,
    )

    # Save the ETag for the batch.complete() call
    etag = response["ETag"]
```

`put_object()` returns a dict containing at least the so important "ETag", needed for later use.

### Multipart Uploads

For [multipart uploads](https://docs.aws.amazon.com/AmazonS3/latest/dev/mpuoverview.html), we have to be aware that:
- The minimum chunk size is 5 MiB.
  But the size of the last chunk can be less than 5 MiB.
- The maximum chunk count is 10,000.

Checks need to be added for those boundaries.
Then, the code is more complex than single uploads, but still quite readable:

```python
# Instantiate a new multipart upload
mpu = s3_client.create_multipart_upload(Bucket="<BUCKET>", Key="<KEY>/<FILENAME>")
upload_id = mpu["UploadId"]

# Parts sent, will be used to complete the multipart upload
data_packs = []

chunk_size = 1024 * 1024 * 5  # Parts of 5 MiB
chunk_count, rest = divmod("<FILESIZE>", chunk_size)
if rest > 0:
    chunk_count += 1

with open("<FILE>", "rb") as fd:
    for idx in range(1, chunk_count + 1):
        # Read a chunk of data
        data = fd.read(chunk_size)

        # Upload it
        part = s3_client.upload_part(
            UploadId=upload_id,
            Bucket="<BUCKET>",
            Key="<KEY>/<FILENAME>",
            PartNumber=idx,
            Body=data,
            ContentLength=len(data),
        )

        # Save the ETag of the uploaded part for later use
        data_packs.append({"ETag": part["ETag"], "PartNumber": part_number})

# Complete the multipart upload
response = s3_client.complete_multipart_upload(
    Bucket="<BUCKET>",
    Key="<KEY>/<FILENAME>",
    UploadId=upload_id,
    MultipartUpload={"Parts": data_packs},
)

# Save the ETag for the batch.complete() call
batch.etag = response["ETag"]
```

This is a simplified version, in real life one would need to handle parallel upload of parts and errors.

#### Resources Consumption

Each and every multipart upload that has been initiated **must** be either completed or aborted. It will not expire, and used resources will not be magically freed.

So to limit the bill, the application must keep somewhere all current uploads and terminate those that are obsolete.

### Upload Completion

When the blob has been uploaded to S3, the Nuxeo server has to be kept up-to-date:

```python
# Let's tell to the server that the S3 upload is finished and can be used
batch.complete()

# And attach the uploaded blob to the document
batch.attach(file.path)
```
