import ssl, xmlrpc.client
import logging

class pkgServerProxy(object):
    def __init__(self, ip, fqdn):
        self.logger = logging.getLogger('davos')
        self.log_level = level = logging.DEBUG #logging.DEBUG
        # Creating SSL context
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_REQUIRED
        self.ctx.load_verify_locations(cafile="/usr/local/share/ca-certificates/pulse-ca-chain.crt")

        context = ssl.create_default_context()
        context.set_ciphers('ALL')

        # Building url (dirty, port and protocol are hardcoded
        # but we are limited by grub command line max length
        # We could pass them if we upgrade to grub2
        self.base_url = "https://%s:9990/" % fqdn

    def __getattr__(self, attr_name):
        # Return the corresponding api proxy according to attr
        url = self.base_url + attr_name + '/'
        return xmlrpc.client.ServerProxy(url, context=self.ctx)

