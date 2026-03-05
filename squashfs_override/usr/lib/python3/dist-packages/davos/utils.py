import os
import subprocess
import random
import base64
import zlib
import json

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
