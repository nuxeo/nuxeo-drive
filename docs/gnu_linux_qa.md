# GNU/Linux - Troubleshooting

## Supported Distributions

This is a table of minimum supported versions.

| Nuxeo Drive | Debian | Ubuntu | Fedora | Manjaro
|---|---|---|---|---
| 4.2.0+ | 10 | 16.04 | 29 | 18.1.0

# No SSL Support on Ubuntu 16.04

This is known and the root cause if the newer versions of Python and PyQt need OpenSSL 1.1 or newer.
Ubuntu 16.04 has OpenSSL 1.0.2.

## No Systray Icon on Fedora 29

You will have to enable the system tray notification area.
