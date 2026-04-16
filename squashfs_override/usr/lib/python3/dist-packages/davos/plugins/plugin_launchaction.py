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

plugin = {"VERSION": "0.1", "NAME":"launchaction", "TYPE":"davos"}

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

def send_log(objectxmpp, proc):
    for line in proc.stdout:
        logger.debug(line)
        objectxmpp.send_log(line)

async def action_mastering(objectxmpp, data):
    def get_dir_size(path='.'):
        total = 0
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    total += get_dir_size(entry.path)
        return total

    logger.error("action_mastering")
    master_path, master_uuid = configure_master(objectxmpp)
    device = get_device()
    yes, process = get_process(objectxmpp, master_uuid, device)

    while True:
        line = await objectxmpp.loop.run_in_executor(None, process.stdout.readline)

        if line.startswith("Ending /usr/sbin/ocs-sr at "):
            break
        if not line:
            break
        if line == "":
            continue
        print(line)
        objectxmpp.send_log(line.strip(), "info")


    await objectxmpp.loop.run_in_executor(None, process.wait)

    yes.terminate()
    process.terminate()

    objectxmpp.send_log("Mastering process finished with return code %s"%process.returncode, "info")

    # Get the size of the master
    # Use local path to get the size, but send the dest path to the relay.
    local_path = os.path.join(objectxmpp.mounts.get("masters").dest, master_uuid)
    master_size = get_dir_size(local_path)

    master_fullpath = os.path.join(master_path, master_uuid)

    datasend={
        "sessionid": objectxmpp.sessionid,
        "from": objectxmpp.boundjid.bare,
        "to": objectxmpp.relay_jid,
        "action":"resultdiskmastering",
        "data":{
            "subaction":"create_master",
            "sessionid": objectxmpp.sessionid,
            "master_uuid": master_uuid,
            "master_path": master_path,
            "master_fullpath": master_fullpath,
            "master_size": master_size,
            "action_id": objectxmpp.action_id,
            "uuid": objectxmpp.uuid,
            "mac": objectxmpp.mac,
            "return_code": process.returncode
        }
    }
    objectxmpp.send_json(objectxmpp.relay_jid, datasend)

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

def configure_master(objectxmpp):
    clonezilla_params = ["-nogui", "-q2", "-c", "-j2", "-z1p", "-i", "100", "-sc", "-p", "true"]

    mpoint = objectxmpp.mounts.get("masters")

    if(mpoint.status() == False):
        mpoint.mount()

    # Define a master name.
    master_uuid = uuid.uuid1().__str__()
    local_path = os.path.join(mpoint.dest, master_uuid)

    while os.path.isdir(local_path) is True:
        master_uuid = uuid.uuid1().__str__()
        local_path = os.path.join(mpoint.dest, master_uuid)

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
    # Clonezilla will work into /home/partimag/master_uuid
    # So /home/partimag must be linked to the master folder in dest:
    # os.symlink(local_path, working_directory)
    os.symlink(mpoint.dest, working_directory)

    # # Create folder for this master.
    # os.makedirs(local_path)

    server_path = os.path.join(mpoint.src, master_uuid)
    objectxmpp.send_log("Create working directory for master %s "%master_uuid, "info")

    # Set Fake Parclone mode
    os.environ['CLMODE'] = 'SAVE_IMAGE'
    return (mpoint.src, master_uuid)


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
    # cmd = 'yes 2>/dev/null|/bin/bash -c "/usr/sbin/ocs-sr %s savedisk %s %s > >(exec cat | tee -a /var/log/davos_saver.log) 2>&1"' % (clonezilla_params, master_uuid, device)
    # error_code = subprocess.call('yes 2>/dev/null|/bin/bash -c "/usr/sbin/ocs-sr %s savedisk %s %s > >(exec cat | tee -a /var/log/davos_saver.log) 2>&1"' % (clonezilla_params, master_uuid, device), shell=True)


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
    """

    # Save image JSON and LOG
    info = {}
    info['title'] = 'Image of %s at %s' % (self.manager.hostname, current_ts)
    info['description'] = ''
    info['size'] = sum(os.path.getsize(image_dir+f) for f in os.listdir(image_dir) if os.path.isfile(image_dir+f))
    info['has_error'] = (error_code != 0)

    log_path = os.path.join(image_dir, 'davos.log')
    json_path = os.path.join(image_dir, 'davosInfo.json')

    try:
        open(log_path, 'w').write(open('/var/log/davos_saver.log', 'r').read())
    except FileNotFoundError:
        self.logger.error("The file /var/log/davos_saver.log does not exist")
    except Exception as e:
        self.logger.error("The error %s occured" % str(e))

    try:
        open(json_path, 'w').write(json.dumps(info))
    except Exception:
        self.logger.error("We failed to write the informations about the master")

"""


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
