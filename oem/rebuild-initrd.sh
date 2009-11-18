#!/bin/sh
# Copyright (c) 2009 Citrix Systems, Inc. All use and distribution of this
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
  echo "Usage: $0 oldinitrd driver.rpm newinitrd"
  exit 1
}

while [ -n "$1" ]; do
  case "$1" in
    --patch=*)
      patch=${1#--patch=};;
    -*)
      usage;;
    *)
      break;
  esac
  shift
done

[ -n "$3" ] || usage
[ -r "$1" ] || die "Cannot open old initrd"
[ -r "$2" ] || die "Cannot open driver RPM"

[ `id -u` -eq 0 ] || die "Must be run as root"

oldinitrd=$1
driverrpm=$2
newinitrd=$3

tmp=/tmp/install-root.$$
[ -n "$VERBOSE" ] && extraflags="v"

rm -rf $tmp
mkdir $tmp
echo "Extracting old initrd..."
zcat $oldinitrd | ( cd $tmp && cpio -id$extraflags )

echo "Extracting driver RPM..."
rpm2cpio $driverrpm | ( cd $tmp && cpio -id$extraflags )

if [ -n "$patch" ]; then
  echo "Applying patch..."
  cat $patch | ( cd $tmp && patch -p0 )
fi

echo "Regenerating dependencies..."
kernelver="`rpm -q --qf "%{PROVIDEVERSION}" -p $driverrpm`xen"
#mv $tmp/lib/modules/$kernelver/extra $tmp/lib/modules/$kernelver/hack
chroot $tmp depmod -a $kernelver

echo "Creating new initrd..."
( cd $tmp && find . | cpio -o$extraflags -H newc | gzip -9c ) > $newinitrd

rm -rf $tmp
echo "Done"
