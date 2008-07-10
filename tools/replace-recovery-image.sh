#!/bin/bash
#
# Citrix XenServer Express edition repack script
#
# Copyright (c) Citrix Systems 2007-2008. All rights reserved.
#
# Xen, the Xen logo, XenCenter, XenMotion are trademarks or registered
# trademarks of Citrix Systems, Inc., in the United States and other
# countries.

help()
{
    echo "usage: replace-recovery-image [-h] <Base ISO> <input image> <Output ISO>"
    echo "the input image should be a bzipped hard drive image"
    echo ""
    echo "options can be:"
    echo "  -h      Displays this help message"
}

if [ `whoami` != root ]; then
    echo "Need to be root to run this script"
    exit 1
fi

# Verify the parameters:
if [ $# -lt 3 ] || [ $1 == 'help' ] || [ $1 == '-h' ]; then
	help
	exit 1
fi

if [ ! -r $1 ];
then
	echo "Could not find the base ISO {$1}"
	exit 2
fi

if [ ! -r $2 ];
then
	echo "Could not find the image {$2}"
	exit 3
fi

echo Using Parameters:
echo Base ISO: 		$1
echo Image To Add:	$2
echo Output ISO: 	$3

# Setup the environment:
DIRSTAGING=$(mktemp -d)
DIRTEMPMOUNT=$(mktemp -d)

rm -f $3

# Copying the contents of the base ISO:
mount -t iso9660 -o loop $1 $DIRTEMPMOUNT
cp -r $DIRTEMPMOUNT/* $DIRSTAGING

# Adding the image:
cp $2 $DIRSTAGING/

# Building the output ISO:
mkisofs -joliet -joliet-long -r \
        -b boot/isolinux/isolinux.bin -c boot/isolinux/boot.cat \
	-no-emul-boot -boot-load-size 4 -boot-info-table \
	-V "XenServer 4.2.0" \
	-o $3 $DIRSTAGING

# Cleaning up the environment:
umount $DIRTEMPMOUNT
