#!/bin/sh
# Copyright (c) 2010 Citrix Systems, Inc. All use and distribution of this
# copyrighted material is governed by and subject to terms and conditions
# as licensed by Citrix Systems, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or
# trademarks of Citrix Systems, Inc. in the United States and/or other 
# countries.

die()
{
  echo "$@" >&2
  exit 2
}

usage()
{
  echo "Usage: $0 oldiso packagedir driver.rpm modules newiso"
  exit 1
}

[ -n "$5" ] || usage
[ -r "$1" ] || die "Cannot open old ISO"
[ -d "$2" ] || die "Cannot open package directory"
[ -r "$3" ] || die "Cannot open driver RPM"

[ `id -u` -eq 0 ] || die "Must be run as root"

oldiso=$1
packagedir=$2
driverrpm=$3
extramodules=$4
newiso=$5

oldtmp=/tmp/oldiso.$$
newtmp=/tmp/newiso.$$

rm -rf $oldtmp
rm -rf $newtmp
mkdir $oldtmp
mkdir $newtmp

mount -o loop,ro $oldiso $oldtmp || die "Failed to mount old ISO"

echo "Copying contents of ISO..."
cp -rp $oldtmp/* $newtmp || die "Failed to copy ISO"

echo "Rebuilding initrd..."
echo
./rebuild-initrd.sh $oldtmp/install.img $driverrpm $newtmp/install.img || die "Failed to rebuild initrd"
umount $oldtmp
echo

echo "Including driver from $packagedir"
mkdir $newtmp/packages.extra
cp -rp $packagedir/* $newtmp/packages.extra
echo "packages.extra" >>$newtmp/XS-REPOSITORY-LIST

sed -e "/APPEND/ s#--- /install#extramodules=$extramodules --- /install#" $newtmp/boot/isolinux/isolinux.cfg >/tmp/isolinux.$$ && \
		mv -f /tmp/isolinux.$$ $newtmp/boot/isolinux/isolinux.cfg

echo "Rebuilding ISO..."
echo '/boot 1000' > /tmp/sort.main.list.$$
mkisofs -joliet -joliet-long -r \
                -b boot/isolinux/isolinux.bin -c boot/isolinux/boot.cat \
                -no-emul-boot -boot-load-size 4 -boot-info-table \
                -sort /tmp/sort.main.list.$$ \
                -V "XenServer-5.5.0 Base Pack" \
                -o $newiso $newtmp
rm -f /tmp/sort.main.list.$$

rm -rf $oldtmp
rm -rf $newtmp
echo "Done"
