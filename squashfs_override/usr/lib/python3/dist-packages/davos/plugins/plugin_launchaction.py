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
import threading

plugin = {"VERSION": "0.055", "NAME":"launchaction", "TYPE":"davos"}

logger = logging.getLogger("davos")

def action(objectxmpp, action, sessionid, data={}, message={}):
    logger.debug("#######################")
    logger.debug("# plugin_%s"%action)
    logger.debug("# sessionid : %s"%sessionid)
    logger.debug("# from : %s"%message["from"])
    logger.debug("# data : %s"%data)
    logger.debug("#######################")


    if "status" not in data:
        return

    objectxmpp.send_log("START ACTION %s"%data["name"], "info")

    # data["status"] = "DONE"
    # logger.debug("%s DONE"%data["name"])
    # return

    if "name" in data:
        # register a new machine
        if data["name"] == "register":
            objectxmpp.loop.create_task(action_register(objectxmpp, data))
    
        # mastering the machine
        elif data["name"] == "mastering":
            objectxmpp.send_log("Starting process", "info")
            objectxmpp.loop.create_task(action_mastering(objectxmpp, data))




        elif data["name"] == "deploy":
            return action_deploy(objectxmpp, data)
    

async def action_register(objectxmpp, data):
    # Change step status
    data["status"] = "WORKING"

    # set hostname
    set_hostname()
    # Generate inventory
    _xml = generate_inventory(objectxmpp, data)
    logger.info("Inventory Generation DONE !")

    datasend = {
        "action": "resultdiskmastering",
        "from": objectxmpp.boundjid.bare,
        "to": objectxmpp.relay_jid,
        "sessionid": objectxmpp.sessionid,
        "data":{
            "subaction":"register",
            "inventory": compress_encode(_xml),
            "action_id": objectxmpp.action_id,
            "uuid":objectxmpp.uuid,
            "mac":objectxmpp.mac
        }
    }

    logger.info("Sending inventory to relay %s"%objectxmpp.relay_jid)
    objectxmpp.send_json(objectxmpp.relay_jid, datasend)

    # End of step execution, change the status to DONE.
    data["status"] = "DONE"

def send_log(objectxmpp, proc):
    for line in proc.stdout:
        logger.debug(line)
        objectxmpp.send_log(line)

async def action_mastering(objectxmpp, data):
    data["status"] = "WORKING"
    master_uuid = configure_master(objectxmpp)
    device = get_device()
    yes, process = get_process(objectxmpp, master_uuid, device)
    while True:
        line = await objectxmpp.loop.run_in_executor(None, process.stdout.readline)

        if line == "":
            continue
        if not line:
            break
        objectxmpp.send_log(line.strip(), "info")

    await objectxmpp.loop.run_in_executor(None, process.wait)

    yes.terminate()

    # TODO: Launch a "done" signal to the relay
    data["status"] = "DONE"

    return


def configure_master(objectxmpp):
    clonezilla_params = ["-nogui", "-q2", "-c", "-j2", "-z1p", "-i", "100", "-sc", "-p", "true"]

    # mpoint is a mounting point between (src)srv:/var/lib/pulse2/imaging/masters and (dest)/imaging_server/masters
    mpoint = objectxmpp.mounts.get("masters")

    if(mpoint.status() == False):
        mpoint.mount()

    # Define a master name.
    master_uuid = uuid.uuid1().__str__()

    # Check if /imaging_server/masters/<uuid> exists already
    while os.path.isdir(os.path.join(mpoint.dest, master_uuid)) is True:
        master_uuid = uuid.uuid1().__str__()

    # Working directory for clonezilla, we have to bind this path to /imaging_server/masters/, where /home/partimag will be a symbolic link.
    working_directory = '/home/partimag'

    # We want to be sure /home/partimag is deleted
    try:
        shutil.rmtree(working_directory, ignore_errors=True)
    except Exception as e:
        pass

    try:
        # In the case we rerun the script in console mode, the sym link is still present.
        os.unlink(working_directory)
    except Exception as e:
        pass

        # link /imaging_server/masters to /home/partimag
    os.symlink(mpoint.dest, working_directory)

    # Create folder for this master. /imaging_server/masters/<uuid>   <-> /home/partimag/<uuid>
    os.makedirs(os.path.join(working_directory, master_uuid))

    objectxmpp.send_log("Create working directory for master %s "%master_uuid, "info")

    # Set Fake Parclone mode
    os.environ['CLMODE'] = 'SAVE_IMAGE'

    return master_uuid


def get_device():
    # Find out the device to save
    if os.path.exists('/dev/nvme0n1'):
        device = 'nvme0n1'
    elif os.path.exists('/dev/sda'):
        device = 'sda'
    elif os.path.exists('/dev/hda'):
        device = 'hda'
    elif os.path.exists('/dev/vda'):
        device = 'vda'

    return device

def get_process(objectxmpp, master_uuid, device):
    cmd = ["/usr/sbin/ocs-sr", "-nogui", "-q2", "-c", "-j2", "-z1p", "-i", "100", "-sc", "-p", "true", "savedisk", master_uuid, device]

    logger.info("Launch SAVE MASTER process: %s"%(" ".join(cmd)))


    # Old command
    # error_code = subprocess.call('yes 2>/dev/null|/bin/bash -c "/usr/sbin/ocs-sr %s savedisk %s %s > >(exec cat | tee -a /var/log/davos_saver.log) 2>&1"' % (" ".join(clonezilla_params), master_uuid, device), shell=True)

    # New command
    # yes in pipe creates a loop to respond automatically "y" on interactive questions
    yes = subprocess.Popen(["yes"], stdout=subprocess.PIPE)
    proc = subprocess.Popen(cmd, stdin=yes.stdout, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    yes.stdout.close()

    return yes, proc


def action_deploy(objectxmpp, data):
    pass


def generate_inventory(objectxmpp, data):
    # Get the inventory agent
    if "inventory_agent" in objectxmpp.kernel_params:
        inventory_agent = objectxmpp.kernel_params["inventory_agent"]
    else:
        inventory_agent = "fusioninventory-agent"

    # Start to generate inventory
    logger.info("Generating inventory...")
    objectxmpp.send_log("Generating inventory...", "info")

    stdout, stderr, status = runInShell('%s --local /tmp --no-category=software,user,process,environment,controller,memory,drive,usb,slot,input,port' % inventory_agent)
    # Check if an error occured
    if status != 0:
        logger.error("Can't find inventory XML file : %s\n%s"%(stdout, stderr))
        return

    logger.info("Inventory /tmp/inventory.ocs file generated successfully !")
    stdout, stderr, status = runInShell('mv /tmp/*.ocs /tmp/inventory.xml')
    # Check if an error occured
    if status != 0:
        logger.error("Can't find inventory XML file : %s\n%s"%(stdout, stderr))
        return

    logger.info("Inventory /tmp/inventory.xml file generated successfully !")
    
    _dom = parse('/tmp/inventory.xml')

    # Replace ARCHNAME, OSNAME and OSCOMMENTS
    # edit_node(_dom, 'ARCHNAME', 'davos-imaging-diskless-env')
    edit_node(_dom, 'OSNAME', 'Unknown operating system (PXE network boot inventory)')
    edit_node(_dom, 'FULL_NAME', 'Unknown operating system (PXE network boot inventory)')
    edit_node(_dom, 'OSCOMMENTS', 'Inventory generated on ' + time.ctime())

    # Exporting XML
    xmldatas = _dom.toxml()
    return xmldatas

def set_hostname():
    hostname = ""
    confirm = False
    while confirm is False:
        # Ask the hostname to the user
        hostname = ""
        try:
            hostname = input("Please enter the machine name: ")
        except:
            pass

        # Empty hostname : retry
        if hostname == "":
            logger.warning(("The hostname %s entered is empty." % hostname))
            continue

        # Check the hostname value validity
        check = False
        if len(hostname) > 255:
            check = False
        if hostname[-1] == ".":
            hostname = hostname[:-1] # strip exactly one dot from the right, if present
        allowed = re.compile(r"(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
        check = all(allowed.match(x) for x in hostname.split("."))

        if check is False:
            logger.warning(("The hostname %s entered is not valid." % hostname))
            hostname = ""
            continue

        answer = ""
        while answer not in ["y", "n"]:
            answer = input("You have entered %s. Is this correct [Y/N]? " % hostname).lower()
        confirm = answer == "y"

    os.environ['HOSTNAME'] = hostname
    runInShell('hostname ' + hostname)
    runInShell('sed -i "s/debian/' + hostname + '/" /etc/hosts')

def edit_node(xmldom, nodename, value, parent=None):
    if parent is None:
        parent = xmldom
    else:
        parent = xmldom.getElementsByTagName(parent)[0]
    try:
        node = parent.getElementsByTagName(nodename)[0]
        node.firstChild.replaceWholeText(value)
    except:
        logger.warning('Cannot set %s to %s', nodename, value)
