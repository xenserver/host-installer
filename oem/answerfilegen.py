#!/usr/bin/env python

import os.path

# values to be customized
hostname = "factory.dell.com"
keybd = "uk"
tz = "Europe/London"
postinstall = "postinstall.sh"

if __name__ == "__main__":
    try:
        boot_disk = os.path.basename(os.readlink("/dev/disk/by-id/edd-int13_dev80"))
    except:
        # fall back to first disk
        boot_disk = 'sda'
        
    print """<?xml version="1.0"?>
   <installation>
      <primary-disk>%s</primary-disk>
      <bootloader location="partition">extlinux</bootloader>
      <keymap>%s</keymap>
      <hostname>%s</hostname>
      <source type="url">file:///tmp/ramdisk/</source>
      <admin-interface name="eth0" proto="dhcp">
      </admin-interface>
      <timezone>%s</timezone>
      <script stage="installation-complete">file:///tmp/ramdisk/%s</script>
   </installation>
""" % (boot_disk, keybd, hostname, tz, postinstall)
