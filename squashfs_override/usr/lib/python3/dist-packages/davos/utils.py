import os
import subprocess
import random
import base64
import zlib
import json
import psutil
import fcntl
import socket
import struct


def runInShell(cmd, *args):
    # If cmd is str and args are not empty remplace them (format)
    if isinstance(cmd, str) and args:
        cmd = cmd % args
    if not isinstance(cmd, list):
        cmd = [cmd]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = process.communicate()
    return out.strip(), err.strip(), process.returncode


class Disk:
    def __init__(self):
        self.dev_media = os.path.join("/", "dev")
        self.name = ""
        if os.path.exists('/dev/nvme0n1'):
            self.name = 'nvme0n1'
        elif os.path.exists('/dev/sda'):
            self.name = 'sda'
        elif os.path.exists('/dev/hda'):
            self.name = 'hda'
        elif os.path.exists('/dev/vda'):
            self.name = 'vda'
        self.disks = [d for d in os.listdir(self.dev_media) if d.startswith(self.name) and d != self.name]



def getRandomName(nb, pref=""):
    a = "abcdefghijklnmopqrstuvwxyz0123456789"
    d = pref
    for t in range(nb):
        d = d + a[random.randint(0, 35)]
    return d


def decode_decompress(content):
    """Decode base64 content string, then decompress the binary"""
    result = zlib.decompress(base64.b64decode(content)).decode("utf-8")
    return result


def compress_encode(content):
    """Compress with zlib and encode in base64 the incoming content.

    Args:
        content (str) : the content to compress and encode

    Returns:
        str: the content compressed and encoded in base64."""

    result = base64.b64encode(zlib.compress(content.encode("utf-8"))).decode("utf-8")
    return result

def network_infos():
    pnic = psutil.net_io_counters(pernic=True)
    stats = {}
    for nicname in list(pnic.keys()):
        stats[nicname] = pnic[nicname].bytes_sent
    interface = max(stats, key=stats.get)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    info = fcntl.ioctl(sock.fileno(), 0x8927,  struct.pack('256s', interface[:15].encode('utf-8')))

    macaddress = ':'.join(['%02x' % char for char in info[18:24]])
    ipaddress = socket.inet_ntoa(fcntl.ioctl(sock.fileno(), 0x8915, struct.pack('256s', interface[:15].encode('utf-8')))[20:24])
    netmask = socket.inet_ntoa(fcntl.ioctl(sock.fileno(), 0x891b, struct.pack('256s', interface.encode('utf-8')))[20:24])

    sock.close()

    return (interface, macaddress, ipaddress, netmask)


class Mount:
    """Class to handle mount command"""
    def __init__(self, src, dest, server=""):
        """Instanciate Mount class, corresponding to a mount point / mount nfs point

        Args:
            self (Mount): Instance of Mount Object
            src (str): source path to mount
            dest (str): dest path where src is mounted. If dest folder doesn't exists it is created
            server (str, default=""): if nfs mount mount server:src into dest
            """
        self.src = src
        self.dest = dest
        self.server = server
        # Initialize is_mounted
        self.is_mounted = False
        # And determine its current state
        self.status()

    def mount(self):
        """Try to mount [server:]src into dest

        Args:
            self (Mount): Instance of Mount Object
        """
        # Already mounted : no need to mount it.
        if self.is_mounted is True:
            return
        # Src or Dest empty, can't mount it, server can be empty
        if self.src == "" or self.dest == "":
            return
        if not os.path.exists(self.dest):
            os.makedirs(self.dest, exist_ok=True)
        # Not mounted : mount it
        if self.server != "":
            cmd = "mount %s:%s %s"%(self.server, self.src, self.dest)
        else:
            cmd = "mount %s %s"%(self.src, self.dest)
        o, e, s = runInShell(cmd)
        if s == 0:
            self.is_mounted = True

    def unmount(self):
        """Unmount the mounted dest if mounted

        Args (self): Instance of Mount Object"""
        if self.status() is False:
            return
        if self.dest == "":
            return
        # Mounted : unmount it
        cmd = "umount %s"%self.dest
        o, e, s = runInShell(cmd)

    def status(self):
        """Get the mount status.

        Args:
            self (Mount): Instance of Mount Object.

        Returns:
            bool: True if the mount point is mounted. Else False"""
        # Update the current state
        self.check_status()
        # return the result
        return self.is_mounted

    def check_status(self):
        """Update the mount status. Used by status, to be sure it's always accurate

        Args:
            (self): Instance of Mount Object."""
        # Check the current state and update it.
        if self.dest == "":
            self.is_mounted = False
        if os.path.isdir(self.dest) is False:
            self.is_mounted = False
        cmd = "cat /proc/mounts | grep %s"%self.dest
        o, e, s = runInShell(cmd)
        if o.decode("utf-8") != "":
            self.is_mounted = True
        else:
            self.is_mounted = False

    def __del__(self):
        """Automatically unmount the mount point when the object is deleted

        Args:
            self (Mount): Instance of Mount Object"""
        self.unmount()
