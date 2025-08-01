# -*- coding: utf-8; -*-
#
# (c) 2007-2015 Mandriva, http://www.mandriva.com/
#
# $Id$
#
# This file is part of Pulse 2, http://pulse2.mandriva.org
#
# Pulse 2 is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Pulse 2 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Pulse 2.  If not, see <http://www.gnu.org/licenses/>.

import os
import subprocess
import json
import time
import socket

class imageSaver(object):

    def __init__(self, manager):

        self.manager = manager
        self.logger = manager.logger
        self.imaging_api = manager.rpc.imaging_api


    def start(self):

        # Get image UUID
        self.image_uuid = self.imaging_api.computerCreateImageDirectory(self.manager.mac)

        # Set Fake Parclone mode
        self.logger.debug('Setting f.clone CLMODE env var to SAVE_IMAGE')
        os.environ['CLMODE'] = 'SAVE_IMAGE'

        # Find out the device to save
        if os.path.exists('/dev/nvme0n1'):
            self.device = 'nvme0n1'
        elif os.path.exists('/dev/sda'):
            self.device = 'sda'
        elif os.path.exists('/dev/hda'):
            self.device = 'hda'
        elif os.path.exists('/dev/vda'):
            self.device = 'vda'

        # Start the image saver
        error_code = subprocess.call('yes 2>/dev/null|/bin/bash -c "/usr/sbin/ocs-sr %s savedisk %s %s > >(exec cat | tee -a /var/log/davos_saver.log) 2>&1"' % (self.manager.clonezilla_params['clonezilla_saver_params'], self.image_uuid, self.device), shell=True)

        # Save image JSON and LOG
        current_ts = time.strftime("%Y%m%d%H%M%S")

        logs_dir = os.path.join('/mnt/logs/debug_imaging/', socket.gethostname()) + '/'
        image_dir = os.path.join('/home/partimag/', self.image_uuid) + '/'

        if error_code != 0:
            os.makedirs(logs_dir, exist_ok=True)
            saver_log_path = os.path.join(logs_dir, 'davos_saver-%s.log' % (current_ts) )
            open(saver_log_path, 'w').write(open('/var/log/davos_saver.log', 'r').read())
            self.logger.warning('An error was encountered while creating image, check davos_saver.log for more details.')
            time.sleep(15)

        # Save image JSON and LOG
        info = {}
        info['title'] = 'Image of %s at %s' % (self.manager.hostname, current_ts)
        info['description'] = ''
        info['size'] = sum(os.path.getsize(image_dir+f) for f in os.listdir(image_dir) if os.path.isfile(image_dir+f))
        info['has_error'] = (error_code != 0)

        log_path = os.path.join(image_dir, 'davos.log')
        json_path = os.path.join(image_dir, 'davosInfo.json')

        try:
            open(log_path, 'w').write(open('/var/log/davos_saver.log', 'r').read())
        except FileNotFoundError:
            self.logger.error("The file /var/log/davos_saver.log does not exist")
        except Exception as e:
            self.logger.error("The error %s occured" % str(e))

        try:
            open(json_path, 'w').write(json.dumps(info))
        except Exception:
            self.logger.error("We failed to write the informations about the master")


        # after an amount of time, xmlrpc goes on "timeout"
        # this try-except is here to "force" xmlrpc to reconnect
        # Thanks to this, the imageDone call will not have a ssl connect problem
        try:
            self.imaging_api.getComputerByMac(self.manager.mac)
        except:
            pass

        # Send save img request
        self.imaging_api.imageDone(self.manager.mac, self.image_uuid)
