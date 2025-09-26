#!/usr/bin/env python3

import configparser
import os
import subprocess
import sys
from typing import List, Optional, Tuple

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


def args_to_cmdline(args: List[str]) -> str:
    def quote_arg(arg):
        if " " not in arg and '"' not in arg and "\\" not in arg:
            return arg
        if "\\" in arg:
            arg = arg.replace("\\", "\\\\")
        if '"' in arg:
            arg = arg.replace('"', '\\"')
        return f'"{arg}"'

    return " ".join(quote_arg(a) for a in args)


def run_process(args: List[str], capture_output: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Executes a process with logging.

    Parameters:
      args[List[str]]: List of arguments
      capture_output[bool]: Whether or not to capture the output and return it.

    Returns:
      success[bool]: Whether or not command was successful
      stdout[Optional[str]]: Stdout string output if capture_output=True
    """
    print("\n* Running: {}".format(args_to_cmdline(args)))
    try:
        result = subprocess.run(args, capture_output=capture_output)
    except Exception as e:
        print(f"* FAILED: {str(e)}")
        return False, None

    if result.returncode != 0:
        print(f"* FAILED (rc={result.returncode})")
        return False, None

    print(f"* SUCCESS")
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
        print("* Running precheck")
        success, stdout = run_process(
            [
                "rsync",
                "--no-motd",
                "--dry-run",
                "--out-format=%n",
                f"{remote}/{precheck_file}",
                f"{dest}/{precheck_file}"
            ],
            capture_output=True
        )
        if not success:
            return False

        if stdout is None or len(stdout) == 0:
            print("* No changes, skipping sync")
            return True

    common_args = [
        "rsync",
        "--verbose",
        "--recursive",
        "--links",
        "--perms",    # Not sure if this is right
        "--times",
        "--devices",  # Doesn't seem right
        "--specials", # Doesn't seem right
        "--sparse",
        "--hard-links",
        "--exclude=*.~tmp~",
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
        success, _ = run_process(common_args + extra_exclude + [ remote,  dest ])
        if not success:
            return False

    final_args = [ "--delete-delay", "--delay-updates" ]

    print("* Running Final Sync")
    success, _ = run_process(common_args + final_args + [ remote, dest ])
    return success


def mirror_sect(config, section_name: str, bwlimit_mbps: int) -> bool:
    print("")
    print("==========")
    if not "name" in config:
        print(f"Missing name in {section_name}")
        return False

    if not "type" in config:
        print(f"Missing type in {config['name']}")
        return False

    if not "remote" in config:
        print(f"Missing remote in {config['name']}")
        return False

    if not "dest" in config:
        print(f"Missing dest in {config['name']}")
        return False

    print(f"* Syncing {config['name']}")
    if config["type"] == "rsync":
        precheck_file = None
        exclude = None
        firststage_exclude = None
        if "precheck_file" in config:
            precheck_file = config["precheck_file"]
        if "exclude" in config:
            exclude = config["precheck_file"].split(",")
        if "firststage_exclude" in config:
            firststage_exclude = config["firststage_exclude"].split(",")
        return rsync(
            config["remote"],
            config["dest"],
            bwlimit_mbps=bwlimit_mbps,
            precheck_file=precheck_file,
            firststage_exclude=firststage_exclude,
            exclude=exclude
        )
    else:
        print(f"Unknown sync type {config['type']}")

    return False


def mirror(config_path: str) -> bool:
    """
    """
    config = configparser.ConfigParser()
    try:
        config.read(config_path)
    except Exception as e:
        print(f"Failed to read config {config_path}: {e}")
        return False

    # Config format
    # [DEFAULT]
    # bwlimit=mbps
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

if not mirror("/etc/mirror.conf"):
    sys.exit(1)

sys.exit(0)
