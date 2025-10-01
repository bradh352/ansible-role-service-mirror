#!/usr/bin/env python3

import configparser
import fcntl
import getpass
import os
import subprocess
import sys
from typing import List, Optional, Tuple

LOCK_FILE = "/tmp/mirror.lock"

def ensuredir(path: str) -> Tuple[bool, Optional[str]]:
    """
    If directory doesn't exist, create it.  Make sure its writable by the current user.

    Parameters:
      path[str]: Directory path

    Returns:
      success[bool]: Whether or not successful
      errmsg[Optional[str]]:  Error message if not successful
    """

    if os.path.exists(path):
        if not os.path.isdir(path):
            return False, "path must be a directory"
        if not os.access(path, os.W_OK):
            return False, "path must be writable"

    try:
        os.makedirs(path, mode=0o755, exist_ok=True)
    except Exception as e:
        return False, f"unable to create path: {str(e)}"

    return True, None


def is_redhat_based():
    """
    Checks if the current system is a Red Hat-based distribution.
    """
    if os.path.exists('/etc/redhat-release'):
        with open('/etc/redhat-release', 'r') as f:
            content = f.read()
            if "Red Hat" in content or "CentOS" in content or "Fedora" in content or \
               "Rocky Linux" in content or "AlmaLinux" in content:
                return True
    return False


def args_to_cmdline(args: List[str]) -> str:
    def quote_arg(arg):
        if " " not in arg and '"' not in arg and "\\" not in arg and "*" not in arg and "|" not in arg:
            return arg
        if "\\" in arg:
            arg = arg.replace("\\", "\\\\")
        if '"' in arg:
            arg = arg.replace('"', '\\"')
        return f'"{arg}"'

    return " ".join(quote_arg(a) for a in args)


def run_process(
    args: List[str],
    capture_output: bool = False,
    retry_codes: Optional[List[int]] = None,
    retry_count: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Executes a process with logging.

    Parameters:
      args[List[str]]: List of arguments
      capture_output[bool]: Whether or not to capture the output and return it.
      retry_codes[Optional[List[int]]]: List of codes eligible for retry
      retry_count[Optional[int]]: Number of times to retry on eligible codes.
        Only relevant if retry_codes is set.  If this isn't set, defaults to 5.

    Returns:
      success[bool]: Whether or not command was successful
      stdout[Optional[str]]: Stdout string output if capture_output=True
    """

    if retry_count is None:
        retry_count = 5

    result = None

    for i in range(retry_count):
        print("\n* Running: {}".format(args_to_cmdline(args)), flush=True)
        try:
            result = subprocess.run(args, capture_output=capture_output)
        except Exception as e:
            print(f"* FAILED: {str(e)}", flush=True)
            return False, None

        if result.returncode == 0:
            break

        if retry_codes is None or result.returncode not in retry_codes:
            break

        print(f"* RETRYING due to rc={result.returncode}", flush=True)

    if result is None:
        raise Exception("The impossible happened. This is making pyright happy")

    if result.returncode != 0:
        print(f"* FAILED (rc={result.returncode})", flush=True)
        return False, None

    print(f"* SUCCESS", flush=True)
    return True, None if not capture_output else result.stdout.decode('utf-8')


def rsync(
    remote: str,
    dest: str,
    bwlimit_mbps: int = 100,
    precheck_file: Optional[str] = None,
    firststage_exclude: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None
) -> bool:
    """
    Perform an rsync of a remote package repository.

    Parameters:
      remote[str]:                             Remote rsync path, e.g. rsync://plug-mirror.rcac.purdue.edu/rocky
      dest[str]:                               Destination directory to hold repository.  e.g. /var/www/rocky
      bwlimit_mbps[int]:                       Bandwidth limit. Defaults to 100Mbps.
      precheck_file[Optional[str]]:            File to check on the remote server to see if rsync is necessary.  If not
                                               specified, will perform the full sync operation.  This is an optimization
                                               and not necessary.
      firststage_exclude[Optional[List[str]]]: When specified, will force a 2-stage sync.  The first sync will exclude
                                               the specified files and NOT delete any existing files.  The second sync
                                               will include the specified files and delete any files locally that no
                                               longer exist on the upstream server.
      exclude[Optional[List[str]]]:            List of files/patterns to always exclude.

    Returns:
      success[bool]: Whether or not sync completed successfully

    Output:
      stdout/stderr are output from the upstream process.
    """

    success, errmsg = ensuredir(dest)
    if not success:
        print(f"destination '{dest}' invalid: {errmsg}", file=sys.stderr)
        return False

    if not remote.endswith("/"):
        remote = remote + "/"

    if not dest.endswith("/"):
        dest = dest + "/"

    if precheck_file is not None:
        print("* Running precheck", flush=True)
        success, stdout = run_process(
            [
                "rsync",
                "--no-motd",
                "--dry-run",
                "--out-format=%n",
                f"{remote}/{precheck_file}",
                f"{dest}/{precheck_file}"
            ],
            capture_output=True,
            retry_codes=[10],
        )
        if not success:
            return False

        if stdout is None or len(stdout) == 0:
            print("* No changes, skipping sync", flush=True)
            return True

    common_args = [
        "rsync",
        "--recursive",
        "--links",
        "--perms",    # Not sure if this is right
        "--times",
        "--devices",  # Doesn't seem right
        "--specials", # Doesn't seem right
        "--sparse",
        "--partial",
        "--hard-links",
        "--exclude=*.~tmp~",
        "--delete-excluded",
        f"--bwlimit={bwlimit_mbps * 1024}"
    ]
    if exclude is not None:
        for pattern in exclude:
            common_args.append(f"--exclude={pattern}")

    if firststage_exclude:
        print("* Running Stage 1")
        extra_exclude = []
        for pattern in firststage_exclude:
            extra_exclude.append(f"--exclude={pattern}")
        success, _ = run_process(common_args + extra_exclude + [ remote,  dest ], retry_codes=[10])
        if not success:
            return False

    final_args = [ "--delete-delay", "--delay-updates" ]

    print("* Running Final Sync", flush=True)
    success, _ = run_process(common_args + final_args + [ remote, dest ], retry_codes=[10])

    if success and is_redhat_based():
        print(f"* Restoring SELinux context on {dest}", flush=True)
        _, _ = run_process([ "restorecon", "-R", dest])

    return success

def debmirror(
    host: str,
    remote_dir: str,
    dest: str,
    dists: List[str],
    arch: List[str],
    sections: List[str],
    bwlimit_mbps: int = 100
) -> bool:
    """
    Perform sync of remote repository using debmirror.

    host [str]:           Remote hostname
    remote_dir [str]:     Remote directory
    dest [str]:           Destination directory for files
    dists [List[str]]:    List of distributions, e.g. [ "jammy", "noble" ]
    arch [List[str]]:     List of archictectures, e.g. [ "amd64", "aarch64" ]
    sections [List[str]]: List of sections, e.g.
                          [ "main", "contrib", "non-free", "main/debian-installer" ]
    bwlimit_mbps[int]:    Bandwidth limit. Defaults to 100Mbps.
    Returns:
      success[bool]: Whether or not sync completed successfully

    Output:
      stdout/stderr are output from the upstream process.
    """
    success, errmsg = ensuredir(dest)
    if not success:
        print(f"destination '{dest}' invalid: {errmsg}", file=sys.stderr)
        return False

    if not dest.endswith("/"):
        dest = dest + "/"

    success, _ = run_process(
        [
            "debmirror",
            "--method=rsync",
            "--diff=none", # Typically most efficient when used with rsync method
            f"--host={host}",
            f"--root={remote_dir}",
            f"--dist={','.join(dists)}",
            f"--arch={','.join(arch)}",
            f"--section={','.join(sections)}",
            "--rsync-batch=10000", # Defaults to 200 which seems low
            "--no-check-gpg",
            f"--rsync-options=-aIL --partial --bwlimit={bwlimit_mbps * 1024}",
            dest,
        ]
    )

    if success and is_redhat_based():
        print(f"* Restoring SELinux context on {dest}", flush=True)
        _, _ = run_process([ "restorecon", "-R", dest])

    return success


def mirror_sect(config, section_name: str, bwlimit_mbps: int) -> bool:
    print("")
    print("==========", flush=True)
    if not "name" in config:
        print(f"Missing name in {section_name}", flush=True)
        return False

    if not "type" in config:
        print(f"Missing type in {config['name']}", flush=True)
        return False

    if not "host" in config:
        print(f"Missing host in {config['name']}", flush=True)
        return False

    if not "remote_dir" in config:
        print(f"Missing remote_dir in {config['name']}", flush=True)
        return False

    if not "dest" in config:
        print(f"Missing dest in {config['name']}", flush=True)
        return False

    print(f"* Syncing {config['name']}", flush=True)
    if config["type"] == "rsync":
        precheck_file = None
        exclude = None
        firststage_exclude = None
        if "rsync_precheck_file" in config:
            precheck_file = config["rsync_precheck_file"]
        if "rsync_exclude" in config:
            exclude = config["rsync_exclude"].split(",")
        if "rsync_firststage_exclude" in config:
            firststage_exclude = config["rsync_firststage_exclude"].split(",")
        return rsync(
            f"rsync://{config['host']}/{config['remote_dir']}",
            config["dest"],
            bwlimit_mbps=bwlimit_mbps,
            precheck_file=precheck_file,
            firststage_exclude=firststage_exclude,
            exclude=exclude
        )
    elif config["type"] == "debmirror":
        return debmirror(
            config["host"],
            config["remote_dir"],
            config["dest"],
            config["deb_dists"].split(","),
            config["deb_arch"].split(","),
            config["deb_sections"].split(","),
            bwlimit_mbps=bwlimit_mbps,
        )
    else:
        print(f"Unknown sync type {config['type']}", flush=True)

    return False


def mirror(config_path: str) -> bool:
    """
    """
    config = configparser.ConfigParser()
    try:
        config.read(config_path)
    except Exception as e:
        print(f"Failed to read config {config_path}: {e}", flush=True)
        return False

    # Config format
    # [DEFAULT]
    # bwlimit=mbps
    # user=nginx
    #
    # [shortname]
    # name=long name
    # type=<type> -- rsync, ...
    # remote=<remote path>
    # dest=<local directory>
    # exclude=<list> -- list of patterns to always exclude
    # precheck_file=<file> -- optional
    # firststage_exclude=<list> -- comma delimited list of excludes for first stage of rsync. Optional.

    bwlimit_mbps=100
    if "DEFAULT" in config:
        if "bwlimit" in config["DEFAULT"]:
            bwlimit_mbps = int(config["DEFAULT"]["bwlimit"])
        if "user" in config["DEFAULT"]:
            if config["DEFAULT"]["user"] != getpass.getuser():
                print(f"Expected to run as user {config['DEFAULT']['user']} but running as {getpass.getuser()}, exiting");
                return False

    failed_mirrors = []

    for section in config.sections():
        if section == "DEFAULT":
            continue

        if "name" in config[section]:
            name = config[section]["name"]
        else:
            name = section

        if not mirror_sect(config[section], section, bwlimit_mbps):
            failed_mirrors.append(name)

    if failed_mirrors:
        print(f"============")
        print(f"failures syncing: { ', '.join(failed_mirrors) }")
        return False

    print(f"* ALL MIRRORS SUCCEEDED")
    return True

def prevent_concurrent_run():
    try:
        lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except IOError:
        print(f"Error: Another instance of the script is already running. Exiting.")
        sys.exit(1)

def release_lock(lock_fd):
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    os.remove(LOCK_FILE)

success = False;
lock_handle = prevent_concurrent_run()
try:
    success = mirror("/etc/mirror.conf")
finally:
    release_lock(lock_handle)

if not success:
    sys.exit(1)

sys.exit(0)
