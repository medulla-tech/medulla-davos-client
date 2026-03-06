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

plugin = {"VERSION": "0.1", "NAME":"launchaction", "TYPE":"davos"}

logger = logging.getLogger("davos")

def action(objectxmpp, action, sessionid, data={}, message={}):
    if "name" in data:
        # register a new machine
        if data["name"] == "register":
            action_register(objectxmpp, data)
    
        # mastering the machine
        elif data["name"] == "mastering":
            action_mastering(objectxmpp, data)

        elif data["name"] == "deploy":
            action_deploy(objectxmpp, data)
    

def action_register(objectxmpp, data):
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

def action_mastering(objectxmpp, data):
    pass


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
