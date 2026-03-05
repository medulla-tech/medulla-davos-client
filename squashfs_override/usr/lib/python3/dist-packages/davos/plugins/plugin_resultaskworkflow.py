import logging
logger = logging.getLogger("davos")

plugin = {"VERSION": "0.1", "NAME": "resultaskworkflow", "TYPE": "davos"}

def action(objectxmpp, action, sessionid, data, message):
    """ Send a ping to relay.plugin_resultdiskmastering"""

    logger.debug("#######################")
    logger.debug("# plugin_%s"%action)
    logger.debug("# sessionid : %s"%sessionid)
    logger.debug("# from : %s"%message["from"])
    logger.debug("# data : %s"%data)
    logger.debug("#######################")


    if data["subaction"] == "getworkflow":
        objectxmpp.send_log("Workflow for action %s received on machine %s"%(objectxmpp.action_id, objectxmpp.uuid), "info")
        if "result" in data:
            if "id" in data["result"]:
                objectxmpp.action_id = data["result"]["id"]
            if "workflow" in data["result"]:
                objectxmpp.workflow = data["result"]["workflow"]
            objectxmpp.execute_workflow(objectxmpp.workflow)