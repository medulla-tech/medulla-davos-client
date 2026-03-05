import logging
logger = logging.getLogger("davos")

plugin = {"VERSION":"0.1", "NAME":"askworkflow", "TYPE":"davos"}

def action(objectxmpp, action, sessionid, data, message):
    """ Send a ping to relay.plugin_resultdiskmastering"""

    logger.debug("#######################")
    logger.debug("# plugin_%s"%action)
    logger.debug("# sessionid : %s"%sessionid)
    logger.debug("# from : %s"%message["from"])
    logger.debug("# data : %s"%data)
    logger.debug("#######################")

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

            logger.debug("send %s to relay"%datasend)
            objectxmpp.send_log("Machine %s asking workflow for action %s to relay"%(objectxmpp.uuid, objectxmpp.action_id), "info")

            # substitute diskmastering jid not set, send it to relay
            objectxmpp.send_json(objectxmpp.relay_jid, datasend)
        else:
            logger.debug("send %s to substitute"%datasend)
            objectxmpp.send_log("Machine %s asking workflow for action %s to substitute"%(objectxmpp.uuid, objectxmpp.action_id), "info")

            # substitute diskmastering jid set, send it directly to
            objectxmpp.send_json(objectxmpp.substitute_jid, datasend)