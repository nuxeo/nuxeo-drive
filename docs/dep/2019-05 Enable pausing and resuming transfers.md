# Enable pausing and resuming transfers

- Created: 2019-05-22
- Last-Modified: 2019-05-22
- Author: Mickaël Schoentgen <mschoentgen@nuxeo.com>,
          Léa Klein <lklein@nuxeo.com>
- Status: implemented
- Related-Ticket: [NXDRIVE-1380](https://jira.nuxeo.com/browse/NXDRIVE-1380)

## Abstract

Allow users to pause and resume ongoing uploads and downloads.

## Rationale

The Nuxeo platform allows people to manage big files, so Drive should be practical to use with them.
Without this feature, users are forced to upload or download a file in one go, unable to exit the Drive app,
and hoping that the server will not cut the connection before the end of it.
Otherwise, they will need to start the transfer all over again.

### Idea

Keeping track of transfers statuses in the database, we could pause and resume them at will.

## Specifications

We need to add database tables for uploads and downloads.
Each entry in one of these tables specifies an unfinished transfer and the necessary data to resume it.

Common data for both types is:
- The path of the transferred file,
- The engine responsible for the transfer,
- Is the transfer initiated by a Direct Edit,
- The progress of the transfer,
- Eventually, the id of the corresponding entry in the States table.

Additionally, downloads require:
- The name of the temporary data file,
- The url used for the download.

Upon resuming, the bytes range left to download can be computed from the size of the temporary data file.

Uploads require:
- The batch id on which to upload,
- The index of the file inside this batch,
- The size of the chunks to upload.


Upon resuming, the chunks left to upload can be retrieved by querying the server with the batch info we saved.


Unfinished transfers can be:
- Ongoing, i.e. they are in the process of being transferred,
- Paused, i.e. they have manually been paused by the user, and have to be manually resumed,
- Suspended, i.e. the synchronization has been suspended,
they'll start again upon manual resuming or an application restart.


Since the transfers are controlled by an iterating loop, we can add a check in between each chunk to see if the status of the transfer entry is still `ONGOING`.

Buttons in the systray can emit a signal to overwrite that status.
