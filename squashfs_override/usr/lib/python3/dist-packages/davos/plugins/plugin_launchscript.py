from davos.utils import *
import logging
import os
import time
from xml.dom.minidom import parse
import psutil
import fcntl
import socket
import struct
import re
import uuid
import subprocess
import shutil
import asyncio
import stat

plugin = {"VERSION": "0.1", "NAME":"launchscript", "TYPE":"davos"}

logger = logging.getLogger("davos")

def action(objectxmpp, action, sessionid, data={}, message={}):
    logger.debug("#######################")
    logger.debug("# plugin_%s"%action)
    logger.debug("# sessionid : %s"%sessionid)
    logger.debug("# from : %s"%message["from"])
    logger.debug("# data : %s"%data)
    logger.debug("#######################")

    # No real step or step already done
    if "status" not in data or data["status"] == "DONE":

        call_next_step(objectxmpp, data)
        return

    # Not a real script
    if "data" not in data or data["data"] == {}:

        call_next_step(objectxmpp, data)
        return

    # Not a real script
    if "content" not in data["data"] or data["data"]["content"] == "":

        call_next_step(objectxmpp, data)
        return

    extension = "sh"
    if "type" in data["data"]:
        if data["data"]["type"] == "sysprep":
            extension = "xml"
        elif data["data"]["type"] == "powershell":
            extension = "ps1"
        elif data["data"]["type"] == "preseed":
            extension = "cfg"

    content = decode_decompress(data["data"]["content"])
    payload = ""

    if "payload" in data["data"]:

        payload = decode_decompress(data["data"]["payload"])

    content_basename="content-%s-%s"%(sessionid, data["step"])
    content_path = os.path.join("/", "tmp", content_basename)

    payload_basename="payload-%s-%s.%s"%(sessionid, data["step"], extension)
    payload_path = os.path.join("/", "tmp", payload_basename)

    # Now we need to write the script and the payload into files
    content = content.replace("@@@filename@@@", payload_basename)

    with open(content_path, "w+") as fb:
        fb.write("#!/bin/bash\n")
        fb.write("\n")
        fb.write(". /usr/lib/libpostinst.sh")
        fb.write("\n")
        # fb.write("set -v\n")
        fb.write("\n")
        fb.write(content)
        fb.write("\n")
        fb.write("echo '### END OF SCRIPT'\n")
        fb.close()
    os.chmod(content_path, stat.S_IRUSR | stat.S_IXUSR)

    with open(payload_path, "w+") as fb:
        fb.write(payload)
        fb.close()

    cmd = ["/bin/bash",  content_path]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    o, e = process.communicate()
    objectxmpp.send_log("%s"%o, "info")
    if e != "":
        objectxmpp.send_log("%s"%e, "error")
    print(o)
    print(e)
    time.sleep(5)

    call_next_step(objectxmpp, data)

    return

async def launch_script(objectxmpp, data, script_path):
    cmd = ["/bin/bash",  script_path]

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    while True:
        line = await objectxmpp.loop.run_in_executor(None, process.stdout.readline)

        if line.startswith("### END OF SCRIPT"):
            break
        if not line:
            break
        if line == "":
            continue
        print(line)
        if line.strip() != "":
            objectxmpp.send_log(line.strip(), "info")

    await objectxmpp.loop.run_in_executor(None, process.wait)

    process.terminate()

    objectxmpp.send_log("Mastering process finished with return code %s"%process.returncode, "info")

def call_next_step(objectxmpp, data):
    objectxmpp.workflow[data["step"]]["status"] = "DONE"
    data["step"] = data["step"] + 1

    datasend={
        "action" : "executeworkflow",
        "sessionid": objectxmpp.sessionid,
        "from": objectxmpp.boundjid.bare,
        "to": objectxmpp.boundjid.bare,
        "data":data
    }
    objectxmpp.send_json(objectxmpp.boundjid.bare, datasend)
    return
