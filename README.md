# Mirror ansible role

Author: Brad House<br/>
License: MIT<br/>
Original Repository: https://github.com/bradh352/ansible-role-service-mirror

## Overview

This role is designed to deploy a repository mirror.

## Variables

- `mirror_bwlimit`: Bandwidth limit in Mbps. Defaults to `100` if not specified.
- `mirror_data_disk`: Location for data disk. Will format this device and
  mount to `mirror_destination`.
- `mirror_destination`: Top level destination for mirrored files. Default is
  `/var/www`.
- `mirror_files`: Explicit list of files to download.  The download is performed
  during the ansible playbook run.  There is no detection performed if the file
  is up to date.  Mainly used for things like downloading known GPG keys.
  - `destdir`: Relative destination directory to `mirror_destination`.
    Directory will be created if it does not exist.
  - `url`: URL of file to download.
  - `filename`: Optional.  Will use the filename from the URL if not specified.
- `mirror_sites`: List of mirrors to maintain, each mirror will contain these
  attributes:
  - `id`: Short identifier for mirror (e.g. `rocky`).  Will be used as part of
    the destination.
  - `name`: Name of Mirror (e.g. `Rocky Linux`)
  - `type`: Type sync to perform. Current options are:
    - `rsync` is prefered for RedHat-based distributions as well as full
      Debian-based distribution clones when the software being mirrored
      supports rsync.
    - `debmirror` used partial debian (and ubuntu) mirrors, or when rsync is not
      available.
    - `reposync` used for RedHat-based distributions when rsync is not
      available.
  - `host`: Remote hostname for repository, E.g. `plug-mirror.rcac.purdue.edu`.
  - `remote_dir`: Remote directory or name, E.g. `rocky`
  - `rsync_exclude`: Optional. Rsync only. List of patterns to exclude from
    sync. See Filter Rules from the rsync manpage for how they are interpreted.
    E.g. `[ "ppc64le/", "riscv64/", "s390x/" ]`
  - `rsync_precheck_file`: Optional. Rsync only. Remote file to check to see if
    mirror is in sync already. E.g. `fullfiletimelist-rocky`
  - `rsync_firststage_exclude`: Optional. Rsync only. List of file patterns to
    exclude from a first-stage sync. Specifying this will also disable file
    deletion during that first sync.  Necessary for debian-based mirrors.
    E.g. `[ "Packages*", "Sources*", "Release*", "InRelease" ]`
  - `deb_dists`: Required for `debmirror`. List of distributions to sync.
    E.g. `["jammy", "jammy-updates", "jammy-security", "noble", "noble-updates", "noble-security"]`
  - `deb_arch`: List of architectures to sync for `debmirror`. Defaults to
    `[ "amd64" ]` if not specified.
  - `deb_sections`: List of debian sections to sync for `debmirror`. Defaults to
    `[ "main", "contrib", "non-free", "main/debian-installer" ]` if not
    specified.
  - `deb_method`: Fetch method to use for debmirror. Options are `rsync`
    and `http`. Defaults to `rsync`.
- `mirror_tls_hostname`: Required. Hostname for TLS certificates
- `mirror_tlscert`: Required. Path to tls certificate.
- `mirror_tlskey`: Required. Path to tls private key.
