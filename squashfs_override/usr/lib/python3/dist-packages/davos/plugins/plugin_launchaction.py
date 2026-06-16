from davos.utils import *
import logging
import os
import time
from xml.dom.minidom import parse
import re
import uuid
import subprocess
import shutil
import asyncio

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

    if "name" in data:
        # register a new machine
        if data["name"] == "register":
            objectxmpp.loop.create_task(action_register(objectxmpp, data))

        # mastering the machine
        elif data["name"] == "mastering":
            objectxmpp.loop.create_task(action_mastering(objectxmpp, data))

        # deploying the machine
        elif data["name"] == "deploy":
            objectxmpp.loop.create_task(action_deploy(objectxmpp, data))
    return


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

    call_next_step(objectxmpp, data)
    return

def send_log(objectxmpp, proc):
    for line in proc.stdout:
        logger.debug(line)
        objectxmpp.send_log(line)

async def action_mastering(objectxmpp, data):

    master_path, master_uuid = configure_master(objectxmpp)
    device = get_device()
    yes, process = master_get_process(objectxmpp, master_uuid, device)

    while True:
        line = await objectxmpp.loop.run_in_executor(None, process.stdout.readline)

        if line.startswith("Ending /usr/sbin/ocs-sr at "):
            break
        if not line:
            break
        if line == "":
            continue
        print(line)
        _line = line.strip()
        if _line != "":
            objectxmpp.send_log(_line, "info")


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

    call_next_step(objectxmpp, data)
    return

def configure_master(objectxmpp):
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
    os.makedirs(local_path)

    server_path = os.path.join(mpoint.src, master_uuid)
    objectxmpp.send_log("Create working directory for master %s "%master_uuid, "info")

    # Set Fake Parclone mode
    os.environ['CLMODE'] = 'SAVE_IMAGE'
    return (mpoint.src, master_uuid)
    # return master_uuid

def configure_deploy(master_path, objectxmpp):
    # The aim of this function is to mount the master_path into /home/partimag
    master_uuid = os.path.basename(master_path)
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

    # Create folder for this /home/partimag
    os.makedirs(working_directory)

    # Create a symbolic link from master_path to /home/partimag/<master_uuid>
    os.symlink(master_path, os.path.join(working_directory, master_uuid))


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

def master_get_process(objectxmpp, master_uuid, device):
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


async def action_deploy(objectxmpp, data):
    mpoint = objectxmpp.mounts.get("masters")

    master_path = os.path.join(mpoint.dest, data["uuid"])

    image_type=check_image_type(master_path, data, objectxmpp)


    if image_type == "unknown" or image_type == "noimage":
        objectxmpp.send_log("Image not supported", "error")
        call_next_step(objectxmpp, data)
        return

    configure_deploy(master_path, objectxmpp)

    master_uuid = os.path.basename(master_path)
    device = get_device()
    # Set Fake Parclone mode
    os.environ['CLMODE'] = 'RESTORE_IMAGE'
    # Find out the device to restore to

    yes, process = deploy_get_process(objectxmpp, master_uuid, device, image_type)

    # Start the image restore
    # if self.mode == 'multicast':
    #     if self.manager.clonezilla_params['clonezilla_restorer_params'] is False:
    #         self.manager.clonezilla_params['clonezilla_restorer_params'] = "-scr -icrc -icds -g auto -e1 auto -e2 -c -r -j2 -p true"

    #     error_code = subprocess.call('yes 2>/dev/null| /bin/bash -c "/usr/sbin/ocs-sr %s --mcast-port 2232 multicast_restoredisk %s %s > >(exec cat | tee -a /var/log/davos_restorer.log) 2>&1"' % (self.manager.clonezilla_params['clonezilla_restorer_params'], self.image_uuid, self.device), shell=True)
    # else:

    # error_code = subprocess.call('yes 2>/dev/null | /bin/bash -c "/usr/sbin/ocs-sr %s restoredisk %s %s > >(exec cat | tee -a /var/log/davos_restorer.log) 2>&1"' % (self.manager.clonezilla_params['clonezilla_restorer_params'], self.image_uuid, self.device), shell=True)
    while True:
        line = await objectxmpp.loop.run_in_executor(None, process.stdout.readline)

        if line.startswith("Ending /usr/sbin/ocs-sr at "):
            break
        if not line:
            break
        if line == "":
            continue
        print(line)
        _line = line.strip()
        if _line != "":
            objectxmpp.send_log(_line, "info")

    await objectxmpp.loop.run_in_executor(None, process.wait)

    yes.terminate()
    process.terminate()

    objectxmpp.send_log("Mastering process finished with return code %s"%process.returncode, "info")

    call_next_step(objectxmpp, data)
    time.sleep(5)
    return



def deploy_get_process(objectxmpp, master_uuid, device, image_type):
    # cmd = 'yes 2>/dev/null|/bin/bash -c "/usr/sbin/ocs-sr %s savedisk %s %s > >(exec cat | tee -a /var/log/davos_saver.log) 2>&1"' % (clonezilla_params, master_uuid, device)
    # error_code = subprocess.call('yes 2>/dev/null|/bin/bash -c "/usr/sbin/ocs-sr %s savedisk %s %s > >(exec cat | tee -a /var/log/davos_saver.log) 2>&1"' % (clonezilla_params, master_uuid, device), shell=True)

    if image_type == "clonezilla":
        os.environ['CLMODE'] = 'RESTORE_IMAGE'

        cmd = ["/usr/sbin/ocs-sr", "-icrc", "-icds", "-nogui", "-g", "auto", "-e1", "auto", "-e2", "-c", "-r", "-j2", "-p", "true", "restoredisk",  master_uuid, device]
        logger.info("Launch Restore MASTER process: %s"%(" ".join(cmd)))

    # TODO: COMPLETE SUPPORT FOR .raw
    # elif image_type.endswith(".raw"):
    #     cmd = f"""dd if=/imaging_server/masters/{master_uuid}/{image_type} of=/dev/{device} bs=1M status=progress;
    #     parted /dev/{device} --fix -s "print";
    #     parted /dev/{device} -s -- mkpart fat32 -1G -1;
    #     parted /dev/{device} set 2 msftdata on

    # """
    yes = subprocess.Popen(["yes"], stdout=subprocess.PIPE)
    proc = subprocess.Popen(cmd, stdin=yes.stdout, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    yes.stdout.close()

    return yes, proc


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


def check_image_type(master_path, data, objectxmpp):

    # Check if the image exists or not
    if not os.path.isdir(master_path):
        objectxmpp.send_log("Could not find image on server", "error")
        call_next_step(objectxmpp, data)
        return "noimage"

    content_list = os.listdir(master_path)
    for elem in content_list:
        # it's the same condition as the next one, but executed before, to have priority over it.
        if elem.endswith(".raw"):
            return elem
        if elem.endswith(".qcow2") or elem.endswith("tar.gz") or elem.endswith("tar.xz"):
            return elem

    # Check if it is a classical "clonezilla" image, or a qcow2 image or a raw image
    if os.path.isfile('%s/davosInfo.json' % master_path):
        return "clonezilla"
    return "unknown"


def get_dir_size(path='.'):
    total = 0
    for path, dirs, files in os.walk(path):
        for f in files:
            total += os.path.getsize(os.path.join(path, f))
    return total


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
