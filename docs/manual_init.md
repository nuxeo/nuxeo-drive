# How to manually initialize a Nuxeo Drive instance

Usually Nuxeo Drive is automatically initialized at first startup. This includes:

- Creation of the configuration folder: `~/.nuxeo-drive`
- Creation of the local folder: `~/.Nuxeo Drive`
- Initialization of the SQLite database: `~/.nuxeo-drive/nxdrive.db`

You might want to do this initialization manually, for example to preset the Nuxeo server URL and proxy configuration before launching Nuxeo Drive the first time.
This can be useful for the deployment of Nuxeo Drive on a large set of desktops, allowing end users to work on a preconfigured instance, only needing to provide their credentials at first startup.

Please note that we only provide UNIX command lines in the following process, they can easily be adapted for Windows.
Of course all this can be scripted.

## Configuration folder and SQLite database file creation

    mkdir ~/.nuxeo-drive
    touch ~/.nuxeo-drive/nxdrive.db

## Device id generation

The `device_config` table of the SQLite database needs a unique id as a primary key of its single row (`device_id` column). You first need to generate this id, for example with Python:

    ataillefer@taillefer-xps:~$ python
    Python 2.7.3 (default, Sep 26 2013, 20:03:06)
    [GCC 4.6.3] on linux2
    Type "help", "copyright", "credits" or "license" for more information.
    >>> import uuid
    >>> uuid.uuid1().hex
    '1bd6686882c111e391a6c8f733c9742b'
    >>> exit()

## SQLite database initialization

1. Connect to the empty SQLite database

        sqlite3 ~/.nuxeo-drive/nxdrive.db

2. Create the `device_config` and `server_bindings` tables

        CREATE TABLE device_config (
            device_id VARCHAR NOT NULL,
            client_version VARCHAR,
            proxy_config VARCHAR,
            proxy_type VARCHAR,
            proxy_server VARCHAR,
            proxy_port VARCHAR,
            proxy_authenticated BOOLEAN,
            proxy_username VARCHAR,
            proxy_password BLOB,
            auto_update BOOLEAN,
            PRIMARY KEY (device_id),
            CHECK (proxy_authenticated IN (0, 1))
        );

        CREATE TABLE server_bindings (
            local_folder VARCHAR NOT NULL,
            server_url VARCHAR,
            remote_user VARCHAR,
            remote_password VARCHAR,
            remote_token VARCHAR,
            server_version VARCHAR,
            update_url VARCHAR,
            last_sync_date INTEGER,
            last_event_log_id INTEGER,
            last_filter_date INTEGER,
            last_ended_sync_date INTEGER,
            last_root_definitions VARCHAR,
            PRIMARY KEY (local_folder)
        );

3. Insert the single row in `device_config`

    Use the previously generated id for the `device_id` column, and set your proxy settings as in the example below.

        INSERT INTO device_config (device_id, proxy_config, proxy_type, proxy_server, proxy_port, proxy_authenticated, auto_update) VALUES ('1bd6686882c111e391a6c8f733c9742b', 'Manual', 'http', '10.218.9.82', '80', 0, 0);

4. Insert a row in `server_bindings`

    Use your local folder path and the Nuxeo server URL.

        INSERT INTO server_bindings (local_folder, server_url) VALUES ('/home/ataillefer/Nuxeo Drive', 'http://10.214.4.90:8080/nuxeo/');

5. Quit SQLite

        .exit

## Start Nuxeo Drive!

The Settings popup should appear waiting for the user's credentials only.
