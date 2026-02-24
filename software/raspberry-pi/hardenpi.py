#!/usr/bin/env python3
"""
Raspberry Pi Hardening Script for Lame Data

Reduces SD card wear and protects against filesystem corruption
from dirty power-offs (battery bank disconnects, unplugging, etc).

Run once after install.sh:
    sudo python3 hardenpi.py          # Apply all hardening
    sudo python3 hardenpi.py --dry-run # Preview changes without applying

Steps performed:
  1. Disable swap (eliminates swap wear on SD card)
  2. Add tmpfs mounts for /tmp and /var/tmp
  3. Set noatime + commit=1 on root filesystem
  4. Install and configure log2ram (logs in RAM, synced on clean shutdown)
  5. Install and configure hardware watchdog (auto-reboot on hang)
  6. Configure overlayroot (optional, requires separate /data partition)
"""

import argparse
import os
import re
import shutil
import subprocess
import sys


DRY_RUN = False


def run(cmd, check=True):
    """Run a shell command, respecting dry-run mode."""
    print(f"  $ {cmd}")
    if DRY_RUN:
        return ""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  STDERR: {result.stderr.strip()}")
        raise subprocess.CalledProcessError(result.returncode, cmd)
    return result.stdout.strip()


def read_file(path):
    """Read a file, return contents or empty string if missing."""
    try:
        with open(path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return ""


def write_file(path, content):
    """Write a file, respecting dry-run mode."""
    print(f"  Writing {path}")
    if DRY_RUN:
        return
    with open(path, 'w') as f:
        f.write(content)


def step_disable_swap():
    """Disable swap to reduce SD card wear."""
    print("\n[1/6] Disabling swap...")

    # Check if swap is active
    swap_output = run("swapon --show", check=False)
    if not swap_output and not os.path.exists("/var/swap"):
        print("  Already disabled, skipping")
        return False

    run("dphys-swapfile swapoff", check=False)
    run("dphys-swapfile uninstall", check=False)
    run("systemctl disable dphys-swapfile", check=False)

    # Remove swap file if it exists
    if os.path.exists("/var/swap"):
        print("  Removing /var/swap")
        if not DRY_RUN:
            os.remove("/var/swap")

    print("  Swap disabled")
    return True


def step_tmpfs_mounts():
    """Add tmpfs mounts for /tmp and /var/tmp in /etc/fstab."""
    print("\n[2/6] Configuring tmpfs mounts...")

    fstab = read_file("/etc/fstab")
    changed = False

    tmpfs_entries = {
        "/tmp": "tmpfs /tmp tmpfs defaults,noatime,nosuid,size=100m 0 0",
        "/var/tmp": "tmpfs /var/tmp tmpfs defaults,noatime,nosuid,size=50m 0 0",
    }

    for mount_point, entry in tmpfs_entries.items():
        # Check if already mounted as tmpfs
        if re.search(rf"^tmpfs\s+{re.escape(mount_point)}\s", fstab, re.MULTILINE):
            print(f"  {mount_point} already tmpfs, skipping")
            continue

        print(f"  Adding tmpfs for {mount_point}")
        fstab = fstab.rstrip("\n") + f"\n{entry}\n"
        changed = True

    if changed:
        write_file("/etc/fstab", fstab)
        print("  Updated /etc/fstab")
    else:
        print("  No changes needed")

    return changed


def step_fstab_root_options():
    """Set noatime and commit=1 on the root filesystem."""
    print("\n[3/6] Optimizing root filesystem mount options...")

    fstab = read_file("/etc/fstab")
    lines = fstab.split("\n")
    changed = False
    new_lines = []

    for line in lines:
        # Match the root mount line (not comments, not blank)
        if re.match(r"^[^#\s]", line) and re.search(r"\s/\s", line):
            parts = line.split()
            if len(parts) >= 4:
                options = parts[3].split(",")

                if "noatime" not in options:
                    # Replace relatime/atime with noatime, or just add it
                    options = [o for o in options if o not in ("relatime", "atime")]
                    options.append("noatime")
                    changed = True

                if not any(o.startswith("commit=") for o in options):
                    options.append("commit=1")
                    changed = True

                parts[3] = ",".join(options)
                line = "\t".join(parts) if "\t" in line else " ".join(parts)

        new_lines.append(line)

    if changed:
        write_file("/etc/fstab", "\n".join(new_lines))
        print(f"  Root mount options updated")
    else:
        print("  Already optimized, skipping")

    return changed


def step_log2ram():
    """Install log2ram to keep logs in RAM."""
    print("\n[4/6] Installing log2ram...")

    # Check if already installed
    result = subprocess.run(
        "systemctl list-unit-files log2ram.service",
        shell=True, capture_output=True, text=True
    )
    if "log2ram.service" in result.stdout:
        print("  Already installed, skipping")
        return False

    # Install log2ram
    print("  Adding log2ram repository...")
    run('echo "deb [signed-by=/usr/share/keyrings/azlux-archive-keyring.gpg] '
        'http://packages.azlux.fr/debian/ bookworm main" | '
        'tee /etc/apt/sources.list.d/azlux.list', check=False)
    run("wget -O /usr/share/keyrings/azlux-archive-keyring.gpg "
        "https://raw.githubusercontent.com/azlux/log2ram/master/log2ram.gpg",
        check=False)
    run("apt-get update -qq", check=False)
    run("apt-get install -y -qq log2ram", check=False)

    # Configure log2ram size
    log2ram_conf = read_file("/etc/log2ram.conf")
    if log2ram_conf:
        log2ram_conf = re.sub(r"^SIZE=.*$", "SIZE=50M", log2ram_conf, flags=re.MULTILINE)
        write_file("/etc/log2ram.conf", log2ram_conf)
        print("  Configured log2ram with 50M RAM disk")

    print("  log2ram installed (active after reboot)")
    return True


def step_watchdog():
    """Install and configure the hardware watchdog."""
    print("\n[5/6] Configuring hardware watchdog...")

    # Check if watchdog is already running
    result = subprocess.run(
        "systemctl is-active watchdog",
        shell=True, capture_output=True, text=True
    )
    if result.stdout.strip() == "active":
        print("  Already active, skipping")
        return False

    # Install watchdog package
    run("apt-get install -y -qq watchdog", check=False)

    # Configure watchdog
    watchdog_conf = """# Lame Data watchdog configuration
# Auto-reboot if the system hangs

watchdog-device = /dev/watchdog
watchdog-timeout = 15
max-load-1 = 24
min-memory = 1
"""
    write_file("/etc/watchdog.conf", watchdog_conf)

    # Enable and start
    run("systemctl enable watchdog", check=False)
    run("systemctl start watchdog", check=False)

    print("  Watchdog configured and enabled")
    return True


def step_overlayroot():
    """Install and configure overlayroot for read-only root filesystem."""
    print("\n[6/6] Configuring overlayroot (read-only root)...")

    # Check for a separate /data partition
    fstab = read_file("/etc/fstab")
    has_data_partition = bool(re.search(r"\s/data\s", fstab))

    if not has_data_partition:
        print("  WARNING: No /data partition found in /etc/fstab.")
        print("  Without a separate writable partition, overlayroot will make")
        print("  ALL writes non-persistent — including your recording data.")
        print("")
        print("  To set up a /data partition:")
        print("    1. When flashing a new SD card, use gparted to create a third partition")
        print("    2. Format it: sudo mkfs.ext4 -L pidata /dev/mmcblk0p3")
        print("    3. Add to /etc/fstab: /dev/mmcblk0p3 /data ext4 defaults,noatime,commit=1 0 2")
        print("    4. Set DATA_DIR=/data in your .env file")
        print("    5. Re-run this script")
        print("")
        print("  Skipping overlayroot for now.")
        return False

    # Check if already installed
    if not os.path.exists("/etc/overlayroot.conf"):
        run("apt-get install -y -qq overlayroot", check=False)

    # Configure overlayroot
    conf = read_file("/etc/overlayroot.conf")
    if 'overlayroot="tmpfs"' in conf:
        print("  Already configured, skipping")
        return False

    # Set overlayroot to use tmpfs overlay
    if conf:
        conf = re.sub(
            r'^overlayroot=.*$',
            'overlayroot="tmpfs"',
            conf,
            flags=re.MULTILINE
        )
    else:
        conf = 'overlayroot="tmpfs"\n'

    write_file("/etc/overlayroot.conf", conf)

    print("  Overlayroot configured (active after reboot)")
    print("  NOTE: To make OS changes in the future, use: sudo overlayroot-chroot")
    return True


def main():
    global DRY_RUN

    parser = argparse.ArgumentParser(
        description="Harden a Raspberry Pi against power loss and SD card wear"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them"
    )
    args = parser.parse_args()
    DRY_RUN = args.dry_run

    # Check root
    if os.geteuid() != 0 and not DRY_RUN:
        print("Error: Run with sudo (or use --dry-run to preview)")
        print("  sudo python3 hardenpi.py")
        sys.exit(1)

    print("=" * 45)
    print("  Lame Data - Pi Hardening")
    if DRY_RUN:
        print("  *** DRY RUN — no changes will be made ***")
    print("=" * 45)

    changes = []

    steps = [
        ("Disable swap", step_disable_swap),
        ("tmpfs mounts", step_tmpfs_mounts),
        ("Root FS options", step_fstab_root_options),
        ("log2ram", step_log2ram),
        ("Watchdog", step_watchdog),
        ("Overlayroot", step_overlayroot),
    ]

    for name, func in steps:
        try:
            changed = func()
            if changed:
                changes.append(name)
        except Exception as e:
            print(f"  ERROR: {e}")
            print(f"  Skipping {name}, continuing...")

    # Summary
    print("\n" + "=" * 45)
    print("  Summary")
    print("=" * 45)

    if changes:
        print(f"\n  Applied {len(changes)} change(s):")
        for c in changes:
            print(f"    - {c}")
        print("\n  >>> REBOOT REQUIRED for changes to take effect <<<")
        print("      sudo reboot")
    else:
        print("\n  No changes needed — already hardened!")

    print("")


if __name__ == "__main__":
    main()
