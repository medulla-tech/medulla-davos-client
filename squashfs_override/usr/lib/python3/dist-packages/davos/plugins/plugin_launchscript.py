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

AGENT_NAME_WINDOWS = "Medulla-Agent-windows-FULL-latest.exe"
AGENT_NAME_LINUX = "Medulla-Agent-linux-MINIMAL-latest.sh"
WORKING_DIR = "/tmp"


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

    download_agents(objectxmpp, data)
    extension = "sh"
    if "type" in data["data"]:
        if data["data"]["type"].lower() == "sysprep":
            extension = "xml"
        elif data["data"]["type"].lower() == "powershell":
            extension = "ps1"
        elif data["data"]["type"].lower() == "preseed":
            extension = "cfg"
        elif data["data"]["type"].lower() == "python":
            extension = "py"

    content = decode_decompress(data["data"]["content"])
    payload = ""

    if "payload" in data["data"]:
        try:
            payload = decode_decompress(data["data"]["payload"])
        except Exception as e:
            print("Error decoding payload : %s"%e)
            payload = ""

    content_basename="content-%s-%s"%(sessionid, data["step"])
    content_path = os.path.join("/", "tmp", content_basename)

    payload_basename="payload-%s-%s.%s"%(sessionid, data["step"], extension)
    payload_path = os.path.join("/", "tmp", payload_basename)

    # Now we need to write the script and the payload into files
    content = content.replace("@@@filename@@@", payload_basename)

    # Change here the machine hostname
    payload = payload.replace("@@@hostname@@@", os.environ.get("HOSTNAME", "localhost"))

    # write the integration script
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

    # write the payload script
    with open(payload_path, "w+") as fb:
        fb.write(payload)
        fb.close()

    # Execute the integration script
    cmd = ["/bin/bash",  content_path]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    o, e = process.communicate()
    objectxmpp.send_log("%s"%o, "info")
    if e != "":
        objectxmpp.send_log("%s"%e, "error")
    print(o)
    print(e)

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


def download_agents(objectxmpp, data):
    if objectxmpp.fullaction is None or objectxmpp.fullaction == {}:
        return False

    if objectxmpp.keyAES32 == "":
        return False

    keyAES32 = objectxmpp.keyAES32
    srv_addr = objectxmpp.srv_addr
    entity_id = objectxmpp.fullaction["entity_id"]

    curl_windows = f"""curl -fL -OJ -H 'Authorization: Bearer {keyAES32}' 'http://{srv_addr}/mmc/mastering/agentdl.php?entity={entity_id}&os=windows'"""
    curl_linux = f"""curl -fL -OJ -H "Authorization: Bearer {keyAES32}" "http://{srv_addr}/mmc/mastering/agentdl.php?entity={entity_id}&os=linux" """

    if os.path.exists(f"{WORKING_DIR}/{AGENT_NAME_WINDOWS}")  is False:
        logger.debug("Downloading windows agent for entity %s"%entity_id)
        o, e, s = runInShell(curl_windows)

        if s == 0:
            shutil.copyfile(f"{AGENT_NAME_WINDOWS}", f"{WORKING_DIR}/{AGENT_NAME_WINDOWS}")
        else:
            logger.debug(f"Download windows agent failed : copying from /opt/winutils")
            if os.path.exists(f"/opt/winutils/{AGENT_NAME_WINDOWS}"):
                try:
                    logger.debug(f"Copying windows agent from /opt/winutils")
                    shutil.copyfile(f"/opt/winutils/{AGENT_NAME_WINDOWS}", f"{WORKING_DIR}/{AGENT_NAME_WINDOWS}")
                except:
                    logger.error(f"Copy windows agent from /opt/winutils failed")

    if os.path.exists(f"{WORKING_DIR}/{AGENT_NAME_LINUX}")  is False:
        logger.debug("Downloading linux agent for entity %s"%entity_id)
        o, e, s = runInShell(curl_linux)

        if s == 0:
            shutil.copyfile(f"{AGENT_NAME_LINUX}", f"{WORKING_DIR}/{AGENT_NAME_LINUX}")
        else:
            logger.debug(f"Download linux agent failed : copying from /opt/linuxutils")
            if os.path.exists(f"/opt/linuxutils/{AGENT_NAME_LINUX}"):
                try:
                    logger.debug(f"Copying linux agent from /opt/linuxutils")
                    shutil.copyfile(f"/opt/linuxutils/{AGENT_NAME_LINUX}", f"{WORKING_DIR}/{AGENT_NAME_LINUX}")
                except Exception as e:
                    logger.error(f"Copy linux agent from /opt/linuxutils failed: {e}")

    if os.path.exists(f"{WORKING_DIR}/{AGENT_NAME_WINDOWS}") is True:
        logger.debug(f"Windows agent is available at {WORKING_DIR}/{AGENT_NAME_WINDOWS}")
    if os.path.exists(f"{WORKING_DIR}/{AGENT_NAME_LINUX}") is True:
        logger.debug(f"Linux agent is available at {WORKING_DIR}/{AGENT_NAME_LINUX}")
