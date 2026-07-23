#!/bin/bash
# See tools/posix/deploy_ci_agent.sh for more information and arguments.

set -e

export OSI="linux"

. "$(python -c "import os.path; print(os.path.realpath('$0').replace('/linux/', '/posix/'))")"

dependencies=(
    "libegl1"
    "libopengl0"
)

remove_excluded_files() {
    # Remove denylisted files known as having bad side effects
    local app_dir="$1"

    echo ">>> [${app_dir}] Removing excluded files"
    while IFS= read -r line; do
        file="$(echo "${line}" | cut -d' ' -f1)"
        if [ ! "${file}" = "" ] && [ ! "${file}" = "#" ]; then
            [ -f "${app_dir}/${file}" ] && rm -fv "${app_dir}/${file}"
        fi
    done < tools/linux/appimage/excludelist

    return 0  # <-- Needed, do not remove!
}

check() {
    # Check AppImage conformity.
    sudo apt-get update && sudo apt-get install -y "${dependencies[@]}"
    echo ">>> [AppImage] Extracting the AppImage"
    cd dist
    [ -f "squashfs-root" ] && rm -rf "squashfs-root"
    ./*-x86_64.AppImage --appimage-extract
    cd ..

    echo ">>> [AppImage] Checking the version"
    ./dist/squashfs-root/AppRun --version

    echo ">>> [AppImage] Checking the AppImage conformity"
    ./tools/linux/appimage/appdir-lint.sh "$(pwd)/dist/squashfs-root"

    echo ">>> [AppImage] Clean-up"
    rm -rf dist/squashfs-root

    return 0  # <-- Needed, do not remove!
}

find_appimage() {
    # Find the AppImage in the dist folder
    shopt -s nullglob
    appimage_files=(dist/*-x86_64.AppImage)
    shopt -u nullglob

    if [ ${#appimage_files[@]} -eq 0 ]; then
        echo ">>> [AppImage] No AppImage found in the dist folder"
        exit 1
    elif [ ${#appimage_files[@]} -gt 1 ]; then
        echo ">>> [AppImage] Multiple AppImages found in the dist folder:"
        for f in "${appimage_files[@]}"; do
            echo "    $f"
        done
        echo ">>> [AppImage] Aborting to prevent signing the wrong file."
        exit 1
    fi

    appimage_file="${appimage_files[0]}"
}

# Locate the file offset and size of the .sha256_sig section reserved by the
# AppImage type-2 runtime. Populates $sig_offset and $sig_size.
locate_sig_section() {
    if ! command -v objdump >/dev/null 2>&1; then
        echo ">>> [AppImage] 'objdump' not found; installing binutils"
        sudo apt-get update && sudo apt-get install -y binutils
    fi

    # objdump -h columns: Idx Name Size VMA LMA File-off Algn
    read sig_offset sig_size < <(
        objdump -h "$appimage_file" \
            | awk '$2==".sha256_sig"{printf "%d %d\n", strtonum("0x"$6), strtonum("0x"$3)}'
    )

    if [ -z "$sig_offset" ] || [ -z "$sig_size" ] || [ "$sig_size" -eq 0 ]; then
        echo ">>> [AppImage] AppImage has no .sha256_sig section; cannot embed signature"
        exit 1
    fi
}

sign() {
    # Import GPG Private Key for signing the AppImage.
    # Feed the key on stdin and silence GPG's stderr so no key UID / key ID
    # metadata is written to CI logs.
    if [ -n "$GPG_PRIVATE_KEY" ]; then
        if ! printf '%s\n' "$GPG_PRIVATE_KEY" \
                | gpg --batch --quiet --import >/dev/null 2>&1; then
            echo ">>> [AppImage] Failed to import GPG private key from GitHub Secrets"
            exit 1
        fi
    fi

    # Check if GPG_PASSPHRASE is set
    if [ -z "$GPG_PASSPHRASE" ]; then
        echo ">>> [AppImage] GPG_PASSPHRASE is not set in GitHub Secrets"
        exit 1
    fi

    find_appimage
    locate_sig_section

    # The .sha256_sig section is pre-allocated (zero-filled) by appimagetool,
    # so we sign the AppImage as-is; the signature will then be embedded into
    # that same section without changing the file size.
    #
    # The passphrase is passed via stdin (--passphrase-fd 0) instead of argv,
    # so it never appears in process listings even on shared runners.
    local detached_sig="${appimage_file}.sig"
    if ! printf '%s' "$GPG_PASSPHRASE" \
            | gpg --batch --yes --quiet --pinentry-mode loopback \
                  --passphrase-fd 0 --armor \
                  --output "$detached_sig" --detach-sign "$appimage_file" \
                  >/dev/null 2>&1; then
        echo ">>> [AppImage] Failed to create detached signature"
        rm -f "$detached_sig"
        exit 1
    fi

    local sig_bytes
    sig_bytes=$(wc -c < "$detached_sig")
    if [ "$sig_bytes" -gt "$sig_size" ]; then
        echo ">>> [AppImage] Signature (${sig_bytes} bytes) exceeds .sha256_sig section (${sig_size} bytes)"
        rm -f "$detached_sig"
        exit 1
    fi

    echo ">>> [AppImage] Embedding signature into ${appimage_file} at offset ${sig_offset} (section size ${sig_size})"
    # dd conv=notrunc writes in place at the exact offset, preserving file size
    # and every other byte of the AppImage.
    dd if="$detached_sig" of="$appimage_file" bs=1 seek="$sig_offset" count="$sig_bytes" conv=notrunc status=none
    if [ $? -ne 0 ]; then
        echo ">>> [AppImage] Failed to embed signature into ${appimage_file}"
        rm -f "$detached_sig"
        exit 1
    fi

    # Embedded-only distribution: drop the standalone detached signature.
    rm -f "$detached_sig"
    chmod +x "$appimage_file"

    echo ">>> [AppImage] Signature embedding successful"
    return 0  # <-- Needed, do not remove!
}

verify_sign() {
    # Check if GPG_KEY_FPR is set
    if [ -z "$GPG_KEY_FPR" ]; then
        echo ">>> [AppImage] GPG_KEY_FPR is not set in GitHub Secrets"
        exit 1
    fi

    # Import GPG Public Key from keyserver. Silence stderr so signer identity
    # (UID / email associated with the key) is not written to CI logs.
    echo ">>> [AppImage] Importing GPG public key from keys.openpgp.org"
    if ! gpg --keyserver hkps://keys.openpgp.org --recv-keys "$GPG_KEY_FPR" \
            >/dev/null 2>&1; then
        echo ">>> [AppImage] Failed to import GPG public key"
        exit 1
    fi

    # Set trust level to ultimate (silence GPG chatter).
    printf '%s:6:\n' "$GPG_KEY_FPR" \
        | gpg --batch --yes --quiet --import-ownertrust >/dev/null 2>&1

    find_appimage
    locate_sig_section

    # Extract the embedded signature block from the .sha256_sig section.
    # The section may contain trailing zero padding after the ASCII-armored
    # signature; keep everything up to and including the END marker.
    local section_dump extracted_sig appimage_zeroed
    section_dump="$(mktemp)"
    extracted_sig="$(mktemp)"
    appimage_zeroed="$(mktemp)"

    dd if="$appimage_file" of="$section_dump" bs=1 skip="$sig_offset" count="$sig_size" status=none
    awk '/^-----END PGP SIGNATURE-----/{print; found=1; exit} {print}' "$section_dump" > "$extracted_sig"

    if [ ! -s "$extracted_sig" ] || ! grep -q -- "-----END PGP SIGNATURE-----" "$extracted_sig"; then
        echo ">>> [AppImage] No embedded PGP signature found in ${appimage_file}"
        rm -f "$section_dump" "$extracted_sig" "$appimage_zeroed"
        exit 1
    fi

    # Reconstruct the bytes that were originally signed: the AppImage with the
    # .sha256_sig section zero-filled (the state before embedding).
    cp "$appimage_file" "$appimage_zeroed"
    dd if=/dev/zero of="$appimage_zeroed" bs=1 seek="$sig_offset" count="$sig_size" conv=notrunc status=none

    # Verify silently; we only need the exit code. Emitting a generic pass/fail
    # message avoids leaking the signer UID that gpg would otherwise print.
    gpg --batch --quiet --verify "$extracted_sig" "$appimage_zeroed" >/dev/null 2>&1
    local verify_rc=$?

    rm -f "$section_dump" "$extracted_sig" "$appimage_zeroed"

    if [ $verify_rc -eq 0 ]; then
        echo ">>> [AppImage] Signature verification successful"
    else
        echo ">>> [AppImage] Signature verification failed"
        exit 1
    fi
}

create_package() {
    # Create the final AppImage
    if [ "$1" = "nuxeo" ]; then
        local app_name="nuxeo-drive"
        local app_id="org.nuxeo.drive"
        app_version="$(grep __version__ nxdrive/__init__.py | cut -d'"' -f2)"
    else
        local app_name="alfresco-drive"
        local app_id="org.alfresco.drive"
        app_version="$(grep __alfresco_version__ nxdrive/__init__.py | cut -d'"' -f2)"
    fi
    app_dir="dist/AppRun"
    output="dist/${app_name}-${app_version}-x86_64.AppImage"

    echo ">>> [AppImage ${app_version}] Adjusting file names to fit in the AppImage"
    # Taken from https://gitlab.com/scottywz/ezpyi/blob/master/ezpyi
    [ -d "${app_dir}" ] && rm -rf "${app_dir}"
    # Move dist/ndrive or dist/alfresco folder to dist/AppRun and rename the executable to AppRun
    if [ "$1" = "nuxeo" ]; then
        mv -v "dist/ndrive" "${app_dir}"
        mv -v "${app_dir}/ndrive" "${app_dir}/AppRun"
    else
        mv -v "dist/alfresco-drive" "${app_dir}"
        mv -v "${app_dir}/alfresco-drive" "${app_dir}/AppRun"
    fi

    echo ">>> [AppImage ${app_version}] Copying icons"
    # Copy icons based on server name to the AppRun folder
    cp -v "tools/linux/${1}/DirIcon.png" "${app_dir}/.DirIcon"
    cp -v "nxdrive/drive/data/icons/app_icon.svg" "${app_dir}/${app_name}.svg"

    echo ">>> [AppImage ${app_version}] Copying metadata files"
    mkdir -pv "${app_dir}/usr/share/metainfo"
    # Copy appdata xml file based on server name to the AppRun folder
    cp -v "tools/linux/${1}/${app_id}.appdata.xml" "${app_dir}/usr/share/metainfo"
    mkdir -pv "${app_dir}/usr/share/applications"
    # Copy appdata desktop file based on server name to the AppRun folder
    cp -v "tools/linux/${1}/${app_id}.desktop" "${app_dir}/usr/share/applications"
    ln -srv "${app_dir}/usr/share/applications/${app_id}.desktop" "${app_dir}/${app_id}.desktop"

    more_compatibility

    echo ">>> [AppImage] Decompressing the AppImage tool"
    cd build
    [ -d "squashfs-root" ] && rm -frv "squashfs-root"
    ./../tools/linux/appimage/appimagetool-x86_64.AppImage --appimage-extract
    cd ..

    echo ">>> [AppImage ${app_version}] Creating the AppImage file"
    # --no-appstream because appstreamcli is not easily installable on CentOS
    ./build/squashfs-root/AppRun --no-appstream "${app_dir}" "${output}"

    echo ">>> [AppImage] Clean-up"
    rm -rf squashfs-root

    return 0  # <-- Needed, do not remove!
}

more_compatibility() {
    echo ">>> [AppImage ${app_version}] Adding more files to expand compatibility"

    # Needed on Fedora 30+ (see https://github.com/slic3r/Slic3r/issues/4798)
    cp -v /usr/lib64/libcrypt-2.17.so "${app_dir}/libcrypt.so.1" || true

    # Needed for Qt 6.5.0+ xcb platform plugin (xcb-cursor0 / libxcb-cursor0)
    cp -v /usr/lib64/libxcb-cursor.so.0 "${app_dir}/libxcb-cursor.so.0" || true

    return 0  # <-- Needed, do not remove!
}

main "$@"
