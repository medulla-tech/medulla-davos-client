import ssl, xmlrpc.client
import logging

class pkgServerProxy(object):
    def __init__(self, ip):
        self.logger = logging.getLogger('davos')
        self.log_level = level = logging.INFO #logging.DEBUG
        self.logger.error('USA')
        # Creating SSL context
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        # Building url (dirty, port and protocol are hardcoded
        # but we are limited by grub command line max length
        # We could pass them if we upgrade to grub2
        self.base_url = "https://%s:9990/" % ip

        self.logger.error('LA URL EST: %s' % self.base_url)
    def __getattr__(self, attr_name):
        # Return the corresponding api proxy according to attr
        url = self.base_url + attr_name + '/'
        return xmlrpc.client.ServerProxy(url, context=self.ctx)

