import logging
logger = logging.getLogger("davos")

plugin = {"VERSION":"0.14", "NAME":"askworkflow", "TYPE":"davos"}

def action(objectxmpp, action, sessionid, data, message):
    """ Send a ping to relay.plugin_resultdiskmastering"""

    logger.debug("#######################")
    logger.debug("# plugin_%s"%action)
    logger.debug("# sessionid : %s"%sessionid)
    logger.debug("# from : %s"%message["from"])
    logger.debug("# data : %s"%data)
    logger.debug("#######################")

    if "subaction" in data:
        if data["subaction"] == "launch":
            if hasattr(objectxmpp, "action_id"):
                datasend = {
                    "from":objectxmpp.boundjid.bare,
                    "action": "diskmastering",
                    "data":{
                        "subaction": "askworkflow",
                        "sessionid": sessionid,
                        "client_jid":objectxmpp.boundjid.bare,
                        "action_id": objectxmpp.action_id,
                        "uuid":objectxmpp.uuid,
                        "mac":objectxmpp.mac
                    },
                    "sessionid": sessionid,
                    "base64":False,
                    "ret":0
                }
                if objectxmpp.substitute_jid == "":
                    datasend["to"] = objectxmpp.relay_jid
                    datasend["action"] = "resultdiskmastering"

                    logger.debug("Machine %s asking workflow for action %s to relay %s"%(objectxmpp.uuid, objectxmpp.action_id, objectxmpp.relay_jid))
                    objectxmpp.send_log("Machine %s asking workflow for action %s to relay %s"%(objectxmpp.uuid, objectxmpp.action_id, objectxmpp.relay_jid), "info")

                    # substitute diskmastering jid not set, send it to relay
                    objectxmpp.send_json(objectxmpp.relay_jid, datasend)
                else:
                    logger.info("Machine %s asking workflow for action %s to substitute %s"%(objectxmpp.uuid, objectxmpp.action_id, objectxmpp.substitute_jid))
                    objectxmpp.send_log("Machine %s asking workflow for action %s to substitute %s"%(objectxmpp.uuid, objectxmpp.action_id, objectxmpp.substitute_jid), "info")

                    # substitute diskmastering jid set, send it directly to
                    objectxmpp.send_json(objectxmpp.substitute_jid, datasend)
        return
