from davos.utils import *
import logging
import os
import time
from xml.dom.minidom import parse
import tftpy
import psutil
import fcntl
import socket
import struct
import re
import uuid
import subprocess
import shutil
import asyncio

plugin = {"VERSION": "0.1", "NAME":"executeworkflow", "TYPE":"davos"}

logger = logging.getLogger("davos")

def action(objectxmpp, action, sessionid, data={}, message={}):
    logger.debug("#######################")
    logger.debug("# plugin_%s"%action)
    logger.debug("# sessionid : %s"%sessionid)
    logger.debug("# from : %s"%message["from"])
    logger.debug("# data : %s"%data)
    logger.debug("#######################")

    step = -1
    count = len(objectxmpp.workflow)

    if "step" not in data:
        step = -1
    else:
        # we can extract step from data only if step is in data.
        try:
            step = int(data["step"])
        except:
            step = -1

    # Can't launch non existing step
    if step >= count:

        step = -1

    status = "TODO"
    # a newer status is stored in cache, we use it as reference to update the workflow.
    if "status" in data:
        status = data["status"]

    objectxmpp.workflow[step]["status"] = status

    # When step = -1, we reached the end of the workflow

    # -1 => end of workflow
    if step == -1:

        objectxmpp.send_log("#### End of workflow", "info")
        datasend = {
            "action" : "resultdiskmastering",
            "sessionid": sessionid,
            "from": objectxmpp.boundjid.bare,
            "to": objectxmpp.relay_jid,
            "data":{
                "subaction":"workflow_done",
                "sessionid": sessionid,
                "uuid": objectxmpp.uuid,
                "mac": objectxmpp.mac,
                "server": objectxmpp.relay_jid,
                "action_id": objectxmpp.action_id
            }
        }

        objectxmpp.send_json(objectxmpp.relay_jid, datasend)

        logger.debug("Workflow done, rebooting the machine in 3 seconds")
        time.sleep(3)
        # runInShell("reboot")
        return

    # Skip wrong steps
    if "status" not in objectxmpp.workflow[step] or objectxmpp.workflow[step] == {}:

        step += 1
        data["step"] = step

    elif objectxmpp.workflow[step]["status"] == "DONE":

        step += 1
        data["step"] = step

    # Launch the currentstep
    elif objectxmpp.workflow[step]["status"] == "TODO":

        objectxmpp.send_log("Executing step <%s> : %s - Type: %s %s"%(step, objectxmpp.workflow[step]["name"], objectxmpp.workflow[step]["type"], objectxmpp.workflow[step]), "info")

        stepaction = "launch%s"%objectxmpp.workflow[step]["type"]
        # stepaction = launchaction | launchscript
        send = {
            "from":objectxmpp.boundjid.bare,
            "to": objectxmpp.boundjid.bare,
            "sessionid": sessionid,
            "action": stepaction,
            "data": objectxmpp.workflow[step]
        }
        # include the step number
        send["data"]["step"] = step

        objectxmpp.send_json(message["from"], send)
        return

    # Stay on the current step,
    elif objectxmpp.workflow[step]["status"] == "WORKING":

        time.sleep(5)

    datasend = {
        "action" : action,
        "sessionid": sessionid,
        "from": message["from"],
        "to": message["to"],
        "data": data
    }
    objectxmpp.send_json(message["from"], datasend)

    return
