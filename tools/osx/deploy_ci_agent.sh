#!/bin/bash
# See tools/posix/deploy_ci_agent.sh for more information and arguments.

set -e

export OSI="osx"

. "$(python3 -c "import os.path; print(os.path.realpath('$0').replace('/osx/', '/posix/'))")"


# Global variables
CODESIGN="codesign                              \
    --options runtime                           \
    --timestamp                                 \
    --entitlements tools/osx/entitlements.plist \
    --sign"

prepare_signing() {
    # Get the identity for code signing the app
    # https://github.com/pyinstaller/pyinstaller/wiki/Recipe-OSX-Code-Signing

    if [ "${SIGNING_ID:-unset}" = "unset" ]; then
        echo ">>> [sign] WARNING: Signing ID is unavailable, application won't be signed."
        return
    elif [ "${KEYCHAIN_PASSWORD:-unset}" = "unset" ]; then
        echo ">>> [sign] WARNING: Keychain is unavailable, application won't be signed."
        return
    fi

    echo ">>> [sign] Unlocking the keychain"
    security unlock-keychain -p "${KEYCHAIN_PASSWORD}" "${KEYCHAIN_PATH}"

    # Allow to use the codesign executable
    security set-key-partition-list -S apple-tool:,apple: -s -k "${KEYCHAIN_PASSWORD}" "${KEYCHAIN_PATH}"

    security find-identity -p codesigning -v "${KEYCHAIN_PATH}" | grep "${SIGNING_ID}" || (
        echo "The '${SIGNING_ID}' identity is not available or no more valid."
        echo "This is the identities list:"
        security find-identity -p codesigning "${KEYCHAIN_PATH}"
        exit 1
    )
}

prepare_signing_from_scratch() {
    # Create and get the identity for code signing the app
    # http://www.tiger-222.fr/?d=2019/11/06/09/40/43-installer-un-certificat-pour-la-signature-de-code-automatique-macos
    # https://docs.travis-ci.com/user/common-build-problems/#mac-macos-sierra-1012-code-signing-errors
    #
    # $1 selects the certificate-import flow, matching the convention used by
    # create_package() and the callers in tools/posix/deploy_ci_agent.sh:
    #   "nuxeo"    -> historical flow: import the .p12 directly with
    #                 `security import` plus the separate drive.priv key.
    #   "alfresco" -> split the .p12 with Homebrew OpenSSL 3 (`-legacy`) into
    #                 individual PEM cert + PKCS#8 key and import each one.
    #                 Required because SecPKCS12Import cannot parse the
    #                 Hyland-provided legacy PKCS#12 archive on macOS 14/15
    #                 ("MAC verification failed" even with the correct
    #                 password).
    local flavor="${1:-nuxeo}"

    if security list-keychains | grep -q "$(basename "${KEYCHAIN_PATH}")"; then
        # Already created at a previous run
        prepare_signing
        return
    fi

    echo ">>> [sign] Create the keychain"
    # Strip any stray CR/LF/tab/space that may have been introduced by the
    # GitHub secret store — `security` reads the -P argument literally, so a
    # trailing character would cause "MAC verification failed" on p12 import.
    KEYCHAIN_PASSWORD="$(printf '%s' "${KEYCHAIN_PASSWORD}" | tr -d '\r\n\t ')"
    security create-keychain -p "${KEYCHAIN_PASSWORD}" "${KEYCHAIN_PATH}"

    echo ">>> [sign] Make the custom keychain default, so xcodebuild will use it for signing"
    security default-keychain -s "${KEYCHAIN_PATH}"

    echo ">>> [sign] Unlock the keychain"
    security unlock-keychain -p "${KEYCHAIN_PASSWORD}" "${KEYCHAIN_PATH}"

    echo ">>> [sign] Add certificates to keychain and allow codesign to access them"
    echo ">>> [sign] Import - AppleIncRootCertificate.cer"
    security import ./AppleIncRootCertificate.cer -t cert -A -k "${KEYCHAIN_PATH}"

    if [ "${flavor}" = "alfresco" ]; then
        # Apple's `security import` (SecPKCS12Import) cannot parse the legacy
        # PKCS#12 archive shipped by Hyland's signing pipeline and fails with
        # "MAC verification failed" on both macOS 14 and macOS 15 even when
        # the password is correct (OpenSSL accepts the same archive +
        # password with no issue). Work around this by using Homebrew's
        # OpenSSL 3 with the `-legacy` provider to split the .p12 into
        # individual PEM cert and unencrypted PKCS#8 key files, then import
        # each one separately - `security import` handles individual PEM
        # files without issue.
        local OPENSSL
        OPENSSL="$(brew --prefix openssl@3)/bin/openssl"
        echo ">>> [sign] Extract cert from developerID_application.p12 using ${OPENSSL}"
        "${OPENSSL}" pkcs12 -in ./developerID_application.p12 -nokeys -clcerts -legacy \
            -passin "pass:${KEYCHAIN_PASSWORD}" \
            -out ./developerID_application.cert.pem
        echo ">>> [sign] Import - developerID_application.cert.pem"
        security import ./developerID_application.cert.pem -t cert -A -k "${KEYCHAIN_PATH}" -T /usr/bin/codesign
        rm -f ./developerID_application.cert.pem

        echo ">>> [sign] Extract private key from developerID_application.p12 using ${OPENSSL}"
        "${OPENSSL}" pkcs12 -in ./developerID_application.p12 -nocerts -nodes -legacy \
            -passin "pass:${KEYCHAIN_PASSWORD}" \
            | "${OPENSSL}" pkcs8 -topk8 -nocrypt -out ./developerID_application.key.pem
        echo ">>> [sign] Import - developerID_application.key.pem"
        security import ./developerID_application.key.pem -t priv -A -T /usr/bin/codesign -k "${KEYCHAIN_PATH}"
        rm -f ./developerID_application.key.pem
    else
        echo ">>> [sign] Import - developerID_application.p12"
        security import ./developerID_application.p12 -k "${KEYCHAIN_PATH}" -P "${KEYCHAIN_PASSWORD}" -A -T /usr/bin/codesign
        echo ">>> [sign] Import - drive.priv"
        security import ./drive.priv -t priv -A -T /usr/bin/codesign -k "${KEYCHAIN_PATH}"
    fi

    echo ">>> [sign] Prepare Signing"
    prepare_signing
}

build_extension() {
    # Create the FinderSync extension, if not already done
    local project_path="${WORKSPACE_DRIVE}/tools/osx/drive/"
    if [ "$1" = "NuxeoFinderSync" ]; then
        local extension_path="${WORKSPACE_DRIVE}/tools/osx/drive/drive.xcodeproj"
    else
        local extension_path="${WORKSPACE_DRIVE}/tools/osx/drive/alfresco-drive.xcodeproj"
    fi

    local entitlement_name="$1"

    echo ">>> [package] Target entitlement ${entitlement_name}"

    echo ">>> [package] Building the FinderSync extension"
    xcodebuild -project "${extension_path}" -target "${entitlement_name}" -configuration Release build
    mv -fv "${project_path}/build/Release/${entitlement_name}.appex" "${WORKSPACE_DRIVE}/${entitlement_name}.appex"
    rm -rf "${project_path}/build"
}

cleanup_local_lsdb_state() {
    # Local-build only: prevent LaunchServices from routing nxdrive:// to
    # stale `org.nuxeo.drive` bundles left over from prior test installs
    # (mounted /Volumes/Nuxeo Drive*, ~/.Trash copies, old DMG mounts, etc.).
    # This does NOT touch the DMG/.app being built, signing, or notarization.
    # CI is skipped: ephemeral runners have no stale state.

    if [ "${GITHUB_WORKSPACE:-unset}" != "unset" ]; then
        return
    fi

    local app="/Applications/Nuxeo Drive.app"
    local lsreg="/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"

    if [ ! -x "${lsreg}" ]; then
        return
    fi

    echo ">>> [local] Cleaning LaunchServices state for org.nuxeo.drive"

    # Quit any running instance to release its Apple Event registration.
    pkill -f "Nuxeo Drive.app/Contents/MacOS/ndrive" 2>/dev/null || true
    sleep 1

    # Detach any mounted Nuxeo Drive DMG volumes.
    for v in /Volumes/Nuxeo\ Drive*; do
        [ -d "${v}" ] || continue
        hdiutil detach "${v}" -force >/dev/null 2>&1 \
            && echo ">>> [local]   detached: ${v}"
    done

    # Prune every stale org.nuxeo.drive bundle from the LaunchServices DB,
    # keeping only the canonical /Applications/Nuxeo Drive.app (if installed).
    local pass cnt
    for pass in 1 2 3; do
        "${lsreg}" -dump 2>/dev/null | awk '
            /^[ \t]*path:[ \t]*(.+)\(0x[0-9a-f]+\)$/ {
                match($0, /path:[ \t]*/); raw=substr($0, RSTART+RLENGTH);
                sub(/[ \t]*\(0x[0-9a-f]+\)[ \t]*$/, "", raw); p=raw; next
            }
            /CFBundleIdentifier = "org\.nuxeo\.drive"/ { if (p) print p }
        ' | sort -u | grep -v "^${app}$" > /tmp/nxd_stale.txt || true
        cnt=$(wc -l < /tmp/nxd_stale.txt | tr -d ' ')
        [ "${cnt}" -eq 0 ] && break
        echo ">>> [local]   pass ${pass}: ${cnt} stale LSDB entries"
        while IFS= read -r p; do "${lsreg}" -u "${p}" >/dev/null 2>&1 || true; done < /tmp/nxd_stale.txt
    done
    rm -f /tmp/nxd_stale.txt

    # Re-register the canonical install (if present) so it's the preferred handler.
    if [ -d "${app}" ]; then
        "${lsreg}" -f "${app}" >/dev/null 2>&1 || true
        echo ">>> [local]   re-registered: ${app}"
    fi
}

create_package() {
    if [ "$1" = "nuxeo" ]; then
        echo ">>> [package] Creating Nuxeo Drive package"
        local app_name="Nuxeo Drive"
        local entitlement_name="NuxeoFinderSync"
    else
        echo ">>> [package] Creating Alfresco Drive package"
        local app_name="Hyland Drive for Alfresco"
        local entitlement_name="AlfrescoFinderSync"
    fi

    # Create the final DMG
    local bundle_name="${app_name}.app"
    local output_dir="${WORKSPACE_DRIVE}/dist"
    local pkg_path="${output_dir}/${bundle_name}"
    local src_folder_tmp="${WORKSPACE}/dmg_src_folder.tmp"
    local dmg_tmp="${WORKSPACE}/${1}-drive.tmp.dmg"
    local background_file="${WORKSPACE_DRIVE}/tools/osx/dmgbackground_${1}.png"
    local extension_path="${WORKSPACE_DRIVE}/tools/osx/drive"
    local entitlements="${extension_path}/${entitlement_name}/${entitlement_name}.entitlements"
    local generated_ds_store="${WORKSPACE_DRIVE}/tools/osx/generated_DS_Store_${1}"
    local app_version

    # Local-build only: prune stale LaunchServices state before producing
    # the new DMG. No-op on CI. See cleanup_local_lsdb_state().
    if [ "$1" = "nuxeo" ]; then
        cleanup_local_lsdb_state
    fi

    build_extension $entitlement_name
    echo ">>> [package] Adding the extension to the package"
    mkdir "${pkg_path}/Contents/PlugIns"
    mv -fv "${WORKSPACE_DRIVE}/${entitlement_name}.appex" "${pkg_path}/Contents/PlugIns/"

    if [ "${GITHUB_WORKSPACE:-unset}" != "unset" ]; then
        prepare_signing_from_scratch "$1"
    else
        prepare_signing
    fi

    if [ "${SIGNING_ID:-unset}" != "unset" ]; then
        echo ">>> [sign] Signing the app and its extension"
        # We recursively sign all the files
        # A message indicating "code object is not signed at all" can appear:
        # This is normal. The find command goes through the binaries in an
        # arbitrary order. When the `codesign` runs, it will look at some
        # dependencies of the current binary and see that they are not signed
        # yet. But the find command will eventually reach it and sign it later.
        find "${pkg_path}/Contents/MacOS" -type f -exec ${CODESIGN} "${SIGNING_ID}" --force {} \;

        # QML libraries need to be signed too for the notarization
        find "${pkg_path}/Contents/Resources" -type f -name "*.dylib" -exec ${CODESIGN} "${SIGNING_ID}" --force {} \;

        find "${pkg_path}" -type f -exec ${CODESIGN} "${SIGNING_ID}" --force {} \;

        # Then we sign the extension
        ${CODESIGN} "${SIGNING_ID}"                  \
                    --force                          \
                    --deep                           \
                    --entitlements "${entitlements}" \
                    "${pkg_path}/Contents/PlugIns/${entitlement_name}.appex"

        # And we shallow sign the .app
        ${CODESIGN} "${SIGNING_ID}" "${pkg_path}" --force

        codesign --display --verbose "${pkg_path}"
        codesign --verbose=4 --deep --strict "${pkg_path}"
        # Diagnostic only. `spctl --assess` runs Gatekeeper against the
        # bundle, which at this point is signed with a valid Developer ID
        # but has not yet been submitted to Apple's notary service (that
        # happens later, against the .dmg produced below). Gatekeeper
        # therefore reports `source=Unnotarized Developer ID` and exits
        # with code 3 -- which under `set -e` would abort the whole
        # pipeline before we ever get a chance to notarize. Swallow the
        # exit code so the output remains visible as a diagnostic without
        # being fatal.
        spctl --assess --verbose "${pkg_path}" || true
    fi

    echo ">>> [package] Creating the DMG file"

    if [ "$app_name" = "Nuxeo Drive" ]; then
        app_version="$(grep __version__ nxdrive/__init__.py | cut -d'"' -f2)"
    else
        app_version="$(grep __alfresco_version__ nxdrive/__init__.py | cut -d'"' -f2)"
    fi
    local dmg_path="${output_dir}/${1}-drive-${app_version}.dmg"

    # Clean-up
    rm -fv "${dmg_path}"
    rm -rf "${src_folder_tmp}" "${dmg_tmp}"
    mkdir "${src_folder_tmp}"

    echo ">>> [DMG] ${bundle_name} version ${app_version}"
    # Compute DMG name and size
    local dmg_size=$(( $(du -sm "${pkg_path}" | cut -d$'\t' -f1,1) + 20 ))
    echo ">>> [DMG ${app_version}] ${dmg_path} (${dmg_size} Mo)"

    echo ">>> [DMG ${app_version}] Preparing the DMG"
    cp -a "${pkg_path}" "${src_folder_tmp}"
    mkdir "${src_folder_tmp}/.background"
    cp "${background_file}" "${src_folder_tmp}/.background"
    cp "${generated_ds_store}" "${src_folder_tmp}/.DS_Store"
    ln -s /Applications "${src_folder_tmp}"

    echo ">>> [DMG ${app_version}] Creating the DMG"
    hdiutil create                         \
            -srcfolder "${src_folder_tmp}" \
            -volname "${app_name}"         \
            -fs HFS+                       \
            -fsargs "-c c=8,a=8,e=8"       \
            -format UDRW                   \
            -size 500           \
            "${dmg_tmp}"

    # -size "${dmg_size}m"           \

    rm -f "${dmg_path}"
    hdiutil convert "${dmg_tmp}" \
            -format UDZO         \
            -imagekey            \
            zlib-level=9         \
            -o "${dmg_path}"

    # Clean tmp directories
    rm -rf "${src_folder_tmp}" "${dmg_tmp}" "${pkg_path}"

    if [ "${SIGNING_ID:-unset}" != "unset" ]; then
        ${CODESIGN} "${SIGNING_ID}" --verbose "dist/${1}-drive-${app_version}.dmg"
        ${PYTHON_VENV} tools/osx/notarize.py "dist/${1}-drive-${app_version}.dmg"
    fi
}

main "$@"
