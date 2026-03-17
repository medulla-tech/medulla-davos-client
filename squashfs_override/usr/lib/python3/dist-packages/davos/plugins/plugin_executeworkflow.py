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

plugin = {"VERSION": "0.306", "NAME":"executeworkflow", "TYPE":"davos"}

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

    if "step" in data:
        try:
            step = int(data["step"])
        except:
            step = -1

    # Can't launch non existing step
    if step >= count:
        step = -1

    # When step = -1, we reached the end of the workflow

    # -1 => end of workflow
    if step == -1:
        objectxmpp.sendlog("#### End of workflow", "info")
        return

    # Skip wrong steps
    if "status" not in objectxmpp.workflow[step] or objectxmpp.workflow[step] == {}:
        step += 1
        data["step"] = step

    # Launch the currentstep
    if objectxmpp.workflow[step]["status"] == "TODO":
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
    if objectxmpp.workflow[step]["status"] == "WORKING":
        time.sleep(5)
    

    if objectxmpp.workflow[step]["status"] == "DONE":
        step += 1
        data["step"] = step

    datasend = {
        "action" : action,
        "sessionid": sessionid,
        "from": message["from"],
        "to": message["to"],
        "data": data
    }
    objectxmpp.send_json(message["from"], datasend)
    logger.error("## End of executeworkflow Execution ##")
    
    return
    
    