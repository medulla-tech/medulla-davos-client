import logging
import json

logger = logging.getLogger("davos")

plugin = {"VERSION":"0.1", "NAME":"ping", "TYPE":"davos"}

def action(objectxmpp, action, sessionid, data={}, message={}):
    """Send a ping to relay.plugin_resultdiskmastering.
    The purpose of ping action is to:
    - send a notify to the relay: machine connected
    - send manifest list: the relay send back plugins to be updated
    """


    logger.debug("#######################")
    logger.debug("# plugin_%s"%action)
    logger.debug("# sessionid : %s"%sessionid)
    logger.debug("# from : %s"%message["from"])
    logger.debug("# data : %s"%data)
    logger.debug("#######################")

    datasend = {
        "from":objectxmpp.boundjid.bare,
        "to":objectxmpp.relay_jid,
        "sessionid":objectxmpp.sessionid,
        "action":"resultdiskmastering",
        "data":{
            "subaction":"ping",
            "sessionid":objectxmpp.sessionid,
            "uuid":objectxmpp.uuid,
            "mac":objectxmpp.mac,
            "server":objectxmpp.relay_jid,
            "manifest" : objectxmpp.plugins.get_loaded_manifest()
        },
        "ret":0,
        "base64":False
    }

    datasend = json.dumps(datasend)
    objectxmpp.send_message(objectxmpp.relay_jid, datasend)
