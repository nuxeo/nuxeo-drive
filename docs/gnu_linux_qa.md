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

## No Systray Icon on Fedora 29

You will have to enable the system tray notification area.
