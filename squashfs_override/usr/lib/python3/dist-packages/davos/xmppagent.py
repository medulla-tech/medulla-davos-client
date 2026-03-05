from slixmpp import ClientXMPP, jid
from slixmpp.xmlstream import handler, matcher
from slixmpp.xmlstream.stanzabase import ET
from slixmpp.exceptions import *

from davos.utils import *
import asyncio
import sys
import logging
import json
import base64
import signal
import os
import importlib.util

logger = logging.getLogger("davos")

logging.getLogger("slixmpp").setLevel(logging.DEBUG)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class PluginManager:
    def __init__(self, objectxmpp):
        self._objectxmpp =  objectxmpp
        self.logger = logger
        self._plugins = {}
        self._loaded_manifest = {}
        self._manifest = {}
        self.load()

    def _load_plugin_from_file(self, module_path):
        """Load a python module from its absolute path. Used on load method and reload method to load plugins.

        Args:
            module_path (str): absolute path to the python file to load.

        Returns:
            module|None: if the module has been successfully loaded, returns the module else returns None
        """

        # Check it has .py extension
        if module_path.endswith(".py") is False:
            self.logger.error("Impossible to load %s : is not a python file"%module_path)
            return None

        # Check if the file exists.
        if os.path.isfile(module_path) is False:
            self.logger.error("Impossible to load %s : file doesn't exist"%module_path)
            return None

        # Get the module name from the filename
        module_name = ""
        module_name = os.path.basename(module_path)
        if module_name.startswith("plugin_") and module_name.endswith(".py"):
            # if module_name equals "plugin_aaa.py", extract "plugin_aaa" as module_name
            module_name = module_name[:-3]
        else:
            self.logger.error("Impossible to load %s : plugin name %s doesn't respect naming convension plugin_XXX.py"%(module_path, module_name))
            return None

        # Try to load the plugin file
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            self.logger.error("Impossible to load %s : %s"%(module_name, e))
            return None
        return module

    def _check_plugin_integrity(self, module):

        # Check if there is a plugin descriptor
        if hasattr(module, "plugin") is False:
            self.logger.error("Plugin Descriptor missing for plugin %s can't use versionning"%module_name)
            return False

        if "VERSION" not in module.plugin:
            self.logger.error("No version found for %s, can't load it because we can't versionning it!"%module_name)
            return False

        if "TYPE" not in module.plugin:
            self.logger.error("No type found for %s, can't verify it's really an appropriate plugin!"%module_name)
            return False

        # Check if the plugin type corresponds to what we want (davos only)
        if module.plugin["TYPE"] != "davos":
            self.logger.error("%s is not a davos plugin, check you are using a \"davos\" type plugin"%module_name)
            return False

        # Check if there is a plugin action
        if hasattr(module, "action") is False:
            self.logger.error("Action function missing for plugin %s, can't load it!"%module_name)
            return False

        return True

    def load(self):
        """get the list of plugins in ./plugins, load them as module and associate the loaded module to a key (based on the plugin name)"""
        self.logger.debug("#### Loading plugins ####")

        # Get the filenames in the /usr/lib/python3/dist-packages/davos/plugins
        plugins_dir = os.path.join(BASE_DIR, "plugins")
        rows = os.listdir(plugins_dir)
        # Only files starting with "plugin_" and finishing with ".py" are accepted
        files = [x for x in rows if x.startswith("plugin_") and x.endswith(".py")]

        # On each file found, do some checks
        for file in files:
            module_name = file[:-3]
            key = file[7:-3]

            # Can't load 2 plugins with the same name
            if key in self._plugins:
                continue

            module_path = os.path.join(plugins_dir, file)

            # Try to load the plugin file
            module = self._load_plugin_from_file(module_path)
            if module is None:
                continue

            if self._check_plugin_integrity(module) is False:
                continue

            self._loaded_manifest[module_name] = module.plugin["VERSION"]

            self._plugins[key] = module
            self.logger.debug("%s Successfully loaded"%key)

    def reload(self, module_names=[]):

        plugins_dir = os.path.join(BASE_DIR, "plugins")

        for module_name in module_names:
            name = module_name[7:]
            # Check on module_name
            if module_name.startswith("plugin_") is False:
                self.logger.error("Impossible to load %s : is not a plugin"%module_name)
                return False

            # Check on absolute path for module_name
            module_path = os.path.join(plugins_dir, "%s.py"%module_name)
            module = self._load_plugin_from_file(module_path)

            if module is None:
                return False

            if self._check_plugin_integrity(module) is False:
                return False

            # Del current module and replace it by the new one only at the end.
            self.logger.debug("=== Updating %s %s => %s"%(module_name, self._plugins[name].plugin["VERSION"], module.plugin["VERSION"]) )
            if name in self._plugins:
                del(self._plugins[name])

            self._plugins[name] = module
            self._manifest[module_name] = module.plugin["VERSION"]

    def has(self, key):
        return key in self._plugins

    def execute(self, action, sessionid, data={}, message=""):
        if self.has(action):
            fnc = self._plugins[action].action
            try:
                fnc(self._objectxmpp, action, sessionid, data, message)
            except Exception as e:
                self.logger.error("Error during %s execution : %s"%(action, e))
                return
    def get_manifest(self):
        return self._manifest

    def get_loaded_manifest(self):
        return self._loaded_manifest

class MUCBot(ClientXMPP):
    def __init__(self, davos_manager, _jid, password, to, srv_addr, srv_port=5222):
        self.logger = logging.getLogger("davos")
        # self.logger.setLevel(logging.INFO)
        try:
            self.srv_port = int(self.srv_port)
        except:
            self.srv_port = 5222
        self.davos_manager = davos_manager
        self.srv_addr = srv_addr
        self.ipv4 = self.srv_addr
        self.address = (self.srv_addr, self.srv_port)

        super().__init__(_jid, password)

        self.add_event_handler("connected", self.handle_connected)
        self.add_event_handler("register", self.register)
        self.add_event_handler("connecting", self.handle_connecting)
        self.add_event_handler("connection_failed", self.handle_connection_failed)
        self.add_event_handler("disconnected", self.handle_disconnected)
        self.add_event_handler("connection_lost", self.handle_connection_lost)
        self.add_event_handler("session_start", self.session_start)
        self.add_event_handler("message", self.message)

        # Declare some registration elements
        self.register_plugin("xep_0030")  # Service Discovery
        self.register_plugin("xep_0045")  # Multi-User Chat
        self.register_plugin("xep_0004")  # Data Forms
        self.register_plugin("xep_0066")
        self.register_plugin("xep_0050")  # Adhoc Commands
        self.register_plugin("xep_0199", {"keepalive": True, "frequency": 600, "interval": 600, "timeout": 500},)
        self.register_plugin("xep_0077")  # In-band Registration
        self["xep_0077"].force_registration = True
        self.shutdown = False

        self.logger.info("self.boundjid = %s"%self.boundjid)
        self.logger.info("self.ipv4 = %s"%self.ipv4)

        self.uuid=""
        self.mac=""
        self.relay_jid = to
        self.action_id = 0
        self.sessionid = getRandomName(8, "davos")
        self.workflow = {}

        self.plugins = PluginManager(self)

    def handle_connecting (self, datas):
        self.logger.debug(f"Try to connect Agent {self.boundjid.bare}")

    def handle_connected(self, datas):
        self.logger.debug(f"Agent {self.boundjid.bare} connected to {datas}")

    def handle_connection_failed(self, data):
        self.logger.error(f"handle_connection_failed on {self.address}")
        self.disconnect()

    def handle_connection_lost(self, data):
        self.logger.error("Connection lost, reason:%s"%data)

    def session_start(self, event):
        self.logger.error("session_start")
        self.send_presence()
        self.get_roster()
        self.send_ping()

    async def register(self, iq):
        """
        Fill out and submit a registration form.

        The form may be composed of basic registration fields, a data form,
        an out-of-band link, or any combination thereof. Data forms and OOB
        links can be checked for as so:

        if iq.match('iq/register/form'):
            # do stuff with data form
            # iq['register']['form']['fields']
        if iq.match('iq/register/oob'):
            # do stuff with OOB URL
            # iq['register']['oob']['url']

        To get the list of basic registration fields, you can use:
            iq['register']['fields']
        """
        self.logger.info("Registration ...")
        resp = self.Iq()
        resp["type"] = "set"
        resp["register"]["username"] = self.boundjid.user
        resp["register"]["password"] = self.password
        try:
            await resp.send()
            self.logger.info("Account created for %s!" % self.boundjid)
        except IqError as e:
            self.logger.warning("Could not register account: %s" % e.iq["error"]["text"])
            # self.disconnect()
        except IqTimeout:
            self.logger.error("No response from server.")
            # self.disconnect()

    async def message(self, msg):
        _from = msg["from"]
        data = {}

        try:
            data = json.loads(msg["body"])
        except Exception as e:
            self.logger.error("Message %s not correctly formated"%(msg["body"], e))
            return

        if "action" not in data:
            self.logger.error("Action missing in message")

        action = data["action"]
        sessionid = data["sessionid"]
        _data = {}
        if "data" in data:
            _data = data["data"]

        # ################# #
        # Launch the plugin #
        # ################# #
        try:
            self.plugins.execute(action, sessionid, _data, msg)
        except Exception as e:
            self.logger.error("Error during %s execution : %s"%(action, e))
            return

    async def stop(self):
        self.logger.debug("Stopping XMPP client...")
        self.disconnect()


    def handle_disconnected(self, data):
        self.logger.debug("Disconnected")

    def send_message(self, to, message):
        super().send_message(mto=to, mbody=message, mtype="chat")

    def send_json(self, to, datas):
        try:
            datasend = json.dumps(datas)
        except:
            return

        super().send_message(mto=to, mbody=datasend, mtype="chat")


    def send_ping(self):
        self.callplugin("ping", self.sessionid)

    def send_log(self, mesg, level="info"):
        datasend = {
            "from":self.boundjid.bare,
            "to":self.toagent,
            "sessionid":self.sessionid,
            "action":"resultdiskmastering",
            "data":{
                "subaction":"log",
                "sessionid":self.sessionid,
                "uuid":self.uuid,
                "mac":self.mac,
                "server":self.relay_jid,
                "level":level,
                "msg":mesg,
            },
            "ret":0,
            "base64":False
        }
        datasend = json.dumps(datasend)
        self.send_message(self.relay_jid, datasend)

    def callplugin(self, key, sessionid, data={}, msg={}):

        if msg == {}:
            msg["from"] = self.boundjid.bare
            msg["sessionid"] = sessionid
        self.plugins.execute(key, sessionid, data, msg)


    def execute_workflow(self, workflow):
        self.send_log("Start Workflow Execution", "info")
        self.logger.debug("Start Workflow Execution")
        i = 0
        for step in workflow:
            self.send_log("Step <%s> %s (type : %s)"%(i, step["name"], step["type"]), "info")
            self.logger.debug("Step <%s> %s (type : %s)"%(i, step["name"], step["type"]))
            self.execute_step(step)
            i += 1

    def execute_step(self, step):
        self.logger.error("Execute step %s"%step)
        