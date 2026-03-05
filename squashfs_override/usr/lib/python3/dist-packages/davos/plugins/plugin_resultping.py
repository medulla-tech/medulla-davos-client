import os
import zlib
import base64
import shutil
import logging
logger = logging.getLogger("davos")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

plugin = {"VERSION": "0.1", "NAME": "resultping", "TYPE": "davos"}

def action(objectxmpp, action, sessionid, data, message):
    """Receive pong from relay, ask the workflow to execute"""

    logger.debug("#######################")
    logger.debug("# plugin_%s"%action)
    logger.debug("# sessionid : %s"%sessionid)
    logger.debug("# from : %s"%message["from"])
    logger.debug("# data : %s"%data)
    logger.debug("#######################")


    if data["subaction"] == "pong":
        if "manifest" in data:
            # Here the plugin name and the plugin content is interesting
            to_reload = []
            for module_name in data["manifest"]:
                content = decode_decompress(data["manifest"][module_name]["content"])

                tmp_module = os.path.join("/", "tmp", "%s.py"%module_name)
                dest_module = os.path.join(BASE_DIR, "%s.py"%module_name)

                with open(tmp_module, "w") as fb:
                    try:
                        fb.write(content)
                    except:
                        os.remove(tmp_module)
                        # Don't copy the void to davos/plugins
                        continue

                shutil.move(tmp_module, dest_module)
                to_reload.append(module_name)

                # Reload all the elements in the to_reload list
                objectxmpp.plugins.reload(to_reload)


        logger.info("Machine %s is ready to work !"%objectxmpp.uuid)
        objectxmpp.send_log("Machine %s is ready to work !"%objectxmpp.uuid, "info")

        # Give the hand to askworkflow plugin
        objectxmpp.callplugin("askworkflow", sessionid, {}, message)


def decode_decompress(content):
    """Decode base64 content string, then decompress the binary"""

    result = zlib.decompress(base64.b64decode(content)).decode("utf-8")

    return result

