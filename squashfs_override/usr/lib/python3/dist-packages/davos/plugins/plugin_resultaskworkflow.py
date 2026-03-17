import logging
import time

logger = logging.getLogger("davos")

plugin = {"VERSION": "0.007", "NAME": "resultaskworkflow", "TYPE": "davos"}

def action(objectxmpp, action, sessionid, data, message):
    """ Receive workflow from relay.plugin_resultdiskmastering or master.diskmastering"""

    logger.debug("#######################")
    logger.debug("# plugin_%s"%action)
    logger.debug("# sessionid : %s"%sessionid)
    logger.debug("# from : %s"%message["from"])
    logger.debug("# data : %s"%data)
    logger.debug("#######################")


    if data["subaction"] == "getworkflow":
        if "result" in data:

            objectxmpp.send_log("Workflow for action %s received on machine %s"%(objectxmpp.action_id, objectxmpp.uuid), "info")
            if "workflow" in data["result"]:

                objectxmpp.fullaction = data["result"]
                objectxmpp.workflow = data["result"]["workflow"]

                for element in objectxmpp.workflow:
                    if "status" not in element:
                        element["status"] = "TODO"
                # objectxmpp.execute_workflow(objectxmpp.workflow)

                datasend = {
                    "from":objectxmpp.boundjid.bare,
                    "to":objectxmpp.boundjid.bare,
                    "action": "executeworkflow",
                    "sessionid":sessionid,
                    "data": {
                        "step":0,
                    }
                }
                objectxmpp.send_log("Calling executeworkflow", "info")

                objectxmpp.send_json(objectxmpp.boundjid.bare, datasend)

                return
            else:
                objectxmpp.send_log("No workflow for action %s"%objectxmpp.action_id)
                logger.error("No workflow for action %s"%objectxmpp.action_id)
                logger.error("Rebooting in 5 secs...")

                # time.sleep(5)
                # objectxmpp.runInShell("reboot")
                return
        else:
            objectxmpp.send_log("No result for action %s"%objectxmpp.action_id)
            logger.error("No result for action %s"%objectxmpp.action_id)
            logger.error("Rebooting in 5 secs...")

            # time.sleep(5)
            # objectxmpp.runInShell("reboot")

            return

    return
