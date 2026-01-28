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

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("davos")
logger.setLevel(logging.INFO)

class MUCBot(ClientXMPP):
    def __init__(self, _jid, password, srv_addr, srv_port=5222):
        self.logger = logging.getLogger("xmpp")
        self.logger.setLevel(logging.INFO)
        try:
            self.srv_port = int(self.srv_port)
        except:
            self.srv_port = 5222

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
        self.register_plugin(
            "xep_0199",
            {"keepalive": True, "frequency": 600, "interval": 600, "timeout": 500},
        )
        self.register_plugin("xep_0077")  # In-band Registration
        self["xep_0077"].force_registration = True
        self.shutdown = False

        self.logger.info("self.boundjid = %s"%self.boundjid)
        self.logger.info("self.ipv4 = %s"%self.ipv4)

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
            self.logger.error("Could not register account: %s" % e.iq["error"]["text"])
            # self.disconnect()
        except IqTimeout:
            self.logger.error("No response from server.")
            # self.disconnect()

    async def message(self, msg):
        msg.reply("===== FROM: %s : Merci pour ce message ===="%msg["from"]).send()

    async def stop(self):
        self.logger.debug("Stopping XMPP client...")
        self.disconnect()


    def handle_disconnected(self, data):
        self.logger.debug("Disconnected")
