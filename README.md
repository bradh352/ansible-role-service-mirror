# Mirror ansible role

Author: Brad House<br/>
License: MIT<br/>
Original Repository: https://github.com/bradh352/ansible-role-service-mirror

## Overview

This role is designed to deploy a repository mirror.

## Variables

- `mirror_bwlimit`: Bandwidth limit in Mbps. Defaults to `100` if not specified.
- `mirror_destination`: Top level destination for mirrored files. Default is
  `/var/www`.
- `mirror_sites`: List of mirrors to maintain, each mirror will contain these
  attributes:
  - `id`: Short identifier for mirror (e.g. `rocky`).  Will be used as part of
    the destination.
  - `name`: Name of Mirror (e.g. `Rocky Linux`)
  - `type`: Type sync to perform, only valid value right now is `rsync`
  - `remote`: Remote URL for repository,
    E.g. `rsync://plug-mirror.rcac.purdue.edu/rocky`
  - `exclude`: Optional. Rsync only. List of patterns to exclude from sync.
    E.g. `[ "ppc64le", "riscv64", "s390x" ]`
  - `precheck_file`: Optional. Rsync only. Remote file to check to see if mirror
    is in sync already. E.g. `fullfiletimelist-rocky`
  - `firststage_exclude`: Optional. Rsync only. List of file patterns to exclude
    from a first-stage sync. Specifying this will also disable file deletion
    during that first sync.  Necessary for debian-based mirrors.
    E.g. `[ "Packages*", "Sources*", "Release*", "InRelease" ]`
- `mirror_dns_email`: Used for certbot to specify email to provider.
- `mirror_dns_provider`: DNS provider in use for performing the DNS-01
  challenge.  Valid values are currently: `godaddy`, `cloudflare`
- `mirror_dns_apikey`: API Key for the DNS provider to be able to create
  a TXT record for `_acme-challenge.{{ inventory_hostname }}`.  This API should
  be restricted to exactly that access and nothing more.  Use `Key:Secret` for
  Godaddy keys. For GoDaddy see some information here:
  https://community.letsencrypt.org/t/godaddy-dns-and-certbot-dns-challenge-scripts/210189
