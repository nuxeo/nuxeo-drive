# GNU/Linux - Troubleshooting

# No SSL Support on Ubuntu 16.04

This is known and the root cause is that newer versions of Python and PyQt need OpenSSL 1.1+.
Ubuntu 16.04 has OpenSSL 1.0.2.

```python
qt.network.ssl: QSslSocket: cannot resolve OPENSSL_init_ssl
qt.network.ssl: QSslSocket: cannot resolve OPENSSL_init_crypto
qt.network.ssl: QSslSocket: cannot resolve ASN1_STRING_get0_data
qt.network.ssl: QSslSocket: cannot resolve EVP_CIPHER_CTX_reset
qt.network.ssl: QSslSocket: cannot resolve RSA_bits
qt.network.ssl: QSslSocket: cannot resolve OPENSSL_sk_new_null
qt.network.ssl: QSslSocket: cannot resolve OPENSSL_sk_push
qt.network.ssl: QSslSocket: cannot resolve OPENSSL_sk_free
qt.network.ssl: QSslSocket: cannot resolve OPENSSL_sk_num
qt.network.ssl: QSslSocket: cannot resolve OPENSSL_sk_pop_free
qt.network.ssl: QSslSocket: cannot resolve OPENSSL_sk_value
qt.network.ssl: QSslSocket: cannot resolve DH_get0_pqg
qt.network.ssl: QSslSocket: cannot resolve SSL_CTX_set_options
qt.network.ssl: QSslSocket: cannot resolve SSL_CTX_set_ciphersuites
qt.network.ssl: QSslSocket: cannot resolve SSL_set_psk_use_session_callback
qt.network.ssl: QSslSocket: cannot resolve SSL_get_client_random
qt.network.ssl: QSslSocket: cannot resolve SSL_SESSION_get_master_key
qt.network.ssl: QSslSocket: cannot resolve SSL_session_reused
qt.network.ssl: QSslSocket: cannot resolve SSL_set_options
qt.network.ssl: QSslSocket: cannot resolve TLS_method
qt.network.ssl: QSslSocket: cannot resolve TLS_client_method
qt.network.ssl: QSslSocket: cannot resolve TLS_server_method
qt.network.ssl: QSslSocket: cannot resolve X509_up_ref
qt.network.ssl: QSslSocket: cannot resolve X509_STORE_CTX_get0_chain
qt.network.ssl: QSslSocket: cannot resolve X509_getm_notBefore
qt.network.ssl: QSslSocket: cannot resolve X509_getm_notAfter
qt.network.ssl: QSslSocket: cannot resolve X509_get_version
qt.network.ssl: QSslSocket: cannot resolve OpenSSL_version_num
qt.network.ssl: QSslSocket: cannot resolve OpenS
```

## No Systray Icon on GNOME (Ubuntu 24+, Fedora, Arch)

GNOME Shell dropped the legacy XEmbed systray protocol in GNOME 3.26.
As a result, `QSystemTrayIcon` (used by Nuxeo Drive) has no tray protocol to connect to on a
default GNOME desktop, and the systray icon will not appear.

The fix is to install and enable the
[AppIndicator and KStatusNotifierItem Support](https://github.com/ubuntu/gnome-shell-extension-appindicator)
GNOME Shell extension, then log out and back in.

### Ubuntu / Debian

Ubuntu often ships with the AppIndicator extension pre-installed but not enabled.
Check first before installing:

```bash
gnome-extensions list | grep -i appindicator
```

You may see one of two extension IDs:

- `ubuntu-appindicators@ubuntu.com` — Ubuntu's built-in version (pre-installed, just needs enabling)
- `appindicatorsupport@rgcjonas.gmail.com` — upstream version

Enable whichever is listed:

```bash
# If you see ubuntu-appindicators@ubuntu.com:
gnome-extensions enable ubuntu-appindicators@ubuntu.com

# If you see appindicatorsupport@rgcjonas.gmail.com:
gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
```

If neither appears, install the package first, then enable:

```bash
sudo apt install gnome-shell-extension-appindicator
gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
```

### Fedora

```bash
sudo dnf install gnome-shell-extension-appindicator
gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
```

### Arch Linux

```bash
sudo pacman -S gnome-shell-extension-appindicator
gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
```

After running the commands for your distribution, **log out and log back in** for the extension to take effect.

Verify it is active with:

```bash
gnome-extensions list --enabled | grep -i appindicator
# expected: appindicatorsupport@rgcjonas.gmail.com
```
