#!/bin/bash
rm -rf nuxeo_drive.egg-info
python setup.py sdist upload -r pypi
