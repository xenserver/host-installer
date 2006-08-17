#!/bin/sh
# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

ROOT_PATH=${1:-"/"}

which_release_file () {
	local ROOT=$1
	test -e "$ROOT/etc/redhat-release" &&
		 printf "redhat-release" && return 0
	test -e "$ROOT/etc/SuSE-release" &&
		 printf "SuSE-release" && return 0
	test -e "$ROOT/etc/fedora-release" &&
		 printf "fedora-release" && return 0
	test -e "$ROOT/etc/debian_version" &&
		 printf "debian_version" && return 0
}

which_os () {
	local filename=$1
	case "$filename" in
	"redhat-release")
		printf "Red Hat"
		;;
	"SuSE-release")
		printf "SuSE"
		;;
	"fedora-release")
		printf "Fedora"
		;;
	"debian_version")
		printf "Debian"
		;;
	*)
		printf "unknown"
		;;
	esac
}

which_distro_version () {
	local distro=$1
	local filename=$2

	local CONTENTS=`cat $filename`

	case "$distro" in
        "Fedora")
		printf "unknown"
                ;;
        "Red Hat")
                # hairy sed call
                # Take a line like:
                # Red Hat Enterprise Linux AS release 3 (Taroon Update 4)
                # and end up with '3.4'
                result=`echo $CONTENTS | sed -e 's/Red Hat Enterprise Linux \(.*\) release //' -e 's/CentOS release //' -e 's/ (\(.*\) Update \([0-9]*\))/\.\2/' -e 's/ (\(.*\))//'`
                printf $result
                ;;
        "SuSE")
		result=`awk '/SUSE LINUX Ent.*/ {dist="sles"; sp="sp1"} /VERSION/ {version=$3} /PATCHLEVEL/ {sp="sp"$3} END {print version sp}' $filename`
                printf $result
                ;;
        *)
                printf "$CONTENTS"
                ;;
        esac
}

release_file=`which_release_file $ROOT_PATH`
distro=`which_os $release_file`
version=`which_distro_version "$distro" $ROOT_PATH/etc/$release_file`

printf "$distro\n$version\n"
exit 0
