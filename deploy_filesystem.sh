#!/bin/bash
#set -e

# =====================================================
# NOTE :
#  This script will be run in a temporary squashfs dir
#  $1 is the original dir on the caller script (build.sh)
# =====================================================

# Copy all fs files to squashfs root
cp -rvf $1/squashfs_override/* ./

# vim instead of vim.tiny
# Very useful for debug
cp usr/bin/vim.tiny usr/bin/vim

# Installing additional packages
mount -t proc none ./proc
mount devpts /dev/pts -t devpts
cp /etc/resolv.conf ./etc/resolv.conf
chroot . bash -c 'mkdir /boot'
chroot . bash -c 'apt update && apt -y install apt-utils python3-minimal libpython3-stdlib fusioninventory-agent dos2unix linux-firmware efivar python3-six python3-pip && exit'

chroot . bash -c 'python3 -m pip install --break-system-packages setuptools'
chroot . bash -c 'python3 -m pip install --break-system-packages tftpy'
chroot . bash -c 'wget https://github.com/glpi-project/glpi-agent/releases/download/1.5/glpi-agent_1.5-1_all.deb'
chroot . bash -c 'apt install ./glpi-agent_1.5-1_all.deb -y '
chroot . bash -c 'rm -fv glpi-agent_1.5-1_all.deb'
chroot . bash -c 'ln -s /usr/lib/systemd/system/sshd.service /etc/systemd/system/multi-user.target.wants/sshd.service'
chroot . bash -c 'rm -frv /opt/*'
chroot . bash -c 'echo efivars >> /etc/modules'
chroot . bash -c 'apt-get autoclean -y '
chroot . bash -c 'apt-get clean -y '
chroot . bash -c 'apt-get autoremove -y '
chroot . bash -c 'find /var/lib/apt/lists/ -maxdepth 1 -type f -exec rm -v {} \;'

# # slixmpp wget command
chroot . bash -c 'wget https://files.pythonhosted.org/packages/8b/1c/6ce021fb5524b41330d583956d1ff8e508c95d6c1bb0ed34790e754cc8d2/slixmpp-1.13.2.tar.gz'
chroot . bash -c 'tar -xvzf slixmpp-1.13.2.tar.gz'
chroot . bash -c 'cp -r slixmpp-1.13.2/slixmpp /usr/lib/python3/dist-packages/'
chroot . bash -c 'rm -frv slixmpp-1.13.2*'


rm -f ./etc/resolv.conf
umount ./proc

# Removing APT cache
rm -rf var/cache/apt

# Skip keymap selection (in deploy mode)
[ -z $DEBUG ] && cat /dev/null > etc/ocs/ocs-live.d/S05-lang-kbd-conf

# Disable kernel low level messages in the console
sed -i 's/^#kernel\.printk.*/kernel.printk = 3 4 1 3/' etc/sysctl.conf
