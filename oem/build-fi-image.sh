#!/bin/sh
# Copyright (c) 2009 Citrix Systems, Inc. All use and distribution of this
# copyrighted material is governed by and subject to terms and conditions
# as licensed by Citrix Systems, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or
# trademarks of Citrix Systems, Inc. in the United States and/or other 
# countries.

usage()
{
  echo "Usage: $0 -o output.zip [ -g answerfilegen ] [ -m mem ] [ -r dev ] [ -s script ] main.iso pack.iso ..." >&2
  exit 2
}

dom0vcpus=4
dom0mem=752
extra_cli=""

while [ -n $1 ]
do
  case "$1" in
    -o)
      output=$2
      shift;;
    -g)
      answerfilegen=$2
      shift;;
    -m)
      dom0mem=$2
      shift;;
    -r)
      extra_cli="$extra_cli make-ramdisk=$2"
      shift;;
    -s)
      script=$2
      shift;;
    -*)
      usage;;
    *)
      break;
  esac
  shift
done

[ -z "$output" ] && usage
[ -n "$answerfilegen" -a ! -r "$answerfilegen" ] && usage
[ -n "$script" -a ! -r "$script" ] && usage

workdir=/tmp/fi-$$
mnt=/tmp/mnt-$$

mkdir -p $workdir
mkdir -p $mnt

if [ -n "$answerfilegen" ]; then
  cp -f $answerfilegen $workdir/answerfilegen
  extra_cli="$extra_cli answerfile_generator=file:///tmp/ramdisk/answerfilegen install"
fi

if [ -n "$script" ]; then
  cp -f $script $workdir
fi

for cdi in $*
do
  mount -o loop,ro $cdi $mnt || break

  if [ -d $mnt/packages.main ]; then
    echo "Copying main ISO files..."
    cp -f $mnt/install.img $workdir
    zcat $mnt/boot/vmlinuz >$workdir/vmlinux
    zcat $mnt/boot/xen.gz >$workdir/xen

    cp -rp $mnt/packages.main $workdir
  elif [ -d $mnt/packages.linux ]; then
    echo "Copying linux ISO files..."
    cp -rp $mnt/packages.linux $workdir
  elif [ -r $mnt/XS-REPOSITORY -a -r $mnt/XS-PACKAGES ]; then
    packname=`sed -ne 's/.*<repository .*originator="\([^"]*\)".*name="\([^"]*\)".*/\1:\2/p' $mnt/XS-REPOSITORY`
    echo "Copying Supplemental Pack $packname"
    packdir=`sed -ne 's/.*<repository .*originator="\([^"]*\)".*name="\([^"]*\)".*/\1#\2/p' $mnt/XS-REPOSITORY`
    mkdir -p $workdir/$packdir
    cp -rp $mnt/* $workdir/$packdir
    echo "$packdir" >>$workdir/XS-REPOSITORY-LIST
  fi
  if [ -r $mnt/XS-REPOSITORY-LIST ]; then
    while read packdir
    do
      [ -d $mnt/$packdir ] || continue
      cp -rp $mnt/$packdir $workdir
      echo "$packdir" >>$workdir/XS-REPOSITORY-LIST
    done <$mnt/XS-REPOSITORY-LIST
  fi

  umount $mnt
done

if ! [ -r $workdir/xen -a -r $workdir/vmlinux -a -r $workdir/install.img ]; then
  echo "ERROR: Failed to find all boot loader files" >&2
  rm -rf $workdir
  exit 1
fi

echo "Creating boot image..."
./mbootpack -o $workdir/bzimage $workdir/xen -m $workdir/vmlinux -m $workdir/install.img
rm -f $workdir/xen $workdir/vmlinux $workdir/install.img

cat >$workdir/xscli <<EOF
dom0_max_vcpus=${dom0vcpus} dom0_mem=${dom0mem}M com1=115200,8n1 console=com1,vga -- xencons=hvc console=hvc0 console=tty0$extra_cli
EOF

echo "Creating zipfile..."
( cd $workdir && zip -r - * ) > $output

rm -rf $workdir
rmdir $mnt

echo "Done."
exit 0
