#!/usr/bin/env python
# Copyright (C) 2006-2007 XenSource Ltd.
# Copyright (C) 2008-2009 Citrix Ltd.
#
# This program is free software; you can redistribute it and/or modify 
# it under the terms of the GNU Lesser General Public License as published 
# by the Free Software Foundation; version 2.1 only.
#
# This program is distributed in the hope that it will be useful, 
# but WITHOUT ANY WARRANTY; without even the implied warranty of 
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the 
# GNU Lesser General Public License for more details.

#########################################################################
#                              NOTICE                                   #
# PLEASE KEEP host-installer.hg/devscan.py AND sm.hg/drivers/devscan.py #
# SYNCHRONISED                                                          #
#########################################################################

import sys, os, re
import glob
import xelogging

def scsiutil_rescan(ids, scanstring='- - -'):
    for id in ids:
        xelogging.log("Rescanning bus id %s with %s" % (id, scanstring))
        path = '/sys/class/scsi_host/host%s/scan' % id
        if os.path.exists(path):
            try:
                f=open(path, 'w')
                f.write('%s\n' % scanstring)
                f.close()
                #time.sleep(2)
            except:
                pass

DEVPATH='/dev/disk/by-id'
DMDEVPATH='/dev/mapper'
SYSFS_PATH1='/sys/class/scsi_host'
SYSFS_PATH2='/sys/class/scsi_disk'
SYSFS_PATH3='/sys/class/fc_transport'

MODULE_INFO = {
    'qlogic': 'QLogic HBA Driver',
    'lpfc': 'Emulex Device Driver for Fibre Channel HBAs',
    'mptfc': 'LSI Logic Fusion MPT Fibre Channel Driver',
    'mptsas': 'LSI Logic Fusion MPT SAS Adapter Driver',
    'megaraid_sas': 'MegaRAID driver for SAS based RAID controllers',
    'xsvhba': 'Xsigo Systems Virtual HBA Driver',
    'mpp': 'RDAC Multipath Handler, manages DELL devices from other adapters'
    }

def gen_QLadt():
    host = []
    arr = glob.glob('/sys/bus/pci/drivers/qla*/*/host*')
    for val in arr:
        host.append(val.split('/')[-1])
    return host

def adapters(filterstr="any"):
    dict = {}
    devs = {}
    adt = {}
    QL = gen_QLadt()
    for a in os.listdir(SYSFS_PATH1):
        if not a in QL:
            proc = match_hbadevs(a, filterstr)
            if not proc:
                continue
        else:
            proc = "qlogic"
        adt[a] = proc
        id = a.replace("host","")
        scsiutil_rescan([id])
        emulex = False
        if proc == "lpfc":
            emulex = True
            path = SYSFS_PATH3
        else:
            path = os.path.join(SYSFS_PATH1,a,"device")
        for i in filter(match_targets,os.listdir(path)):
            tgt = i.replace('target','')
            if emulex:
                sysfs = os.path.join(SYSFS_PATH3,i,"device")
            else:
                sysfs = SYSFS_PATH2
            for lun in os.listdir(sysfs):
                if not match_LUNs(lun,tgt):
                    continue
                if emulex:
                    dir = os.path.join(sysfs,lun)
                else:
                    dir = os.path.join(sysfs,lun,"device")
                for dev in filter(match_dev,os.listdir(dir)):
                    key = dev.replace("block:","")
                    entry = {}
                    entry['procname'] = proc
                    entry['host'] =id
                    entry['target'] = lun
                    devs[key] = entry
        # for new qlogic sysfs layout (rport under device, then target)
        for i in filter(match_rport,os.listdir(path)):
            newpath = os.path.join(path, i)
            for j in filter(match_targets,os.listdir(newpath)):
                tgt = j.replace('target','')
                sysfs = SYSFS_PATH2
                for lun in os.listdir(sysfs):
                    if not match_LUNs(lun,tgt):
                        continue
                    dir = os.path.join(sysfs,lun,"device")
                    for dev in filter(match_dev,os.listdir(dir)):
                        key = dev.replace("block:","")
                        entry = {}
                        entry['procname'] = proc
                        entry['host'] = id
                        entry['target'] = lun
                        devs[key] = entry

        # for new mptsas sysfs entries, check for phy* node
        for i in filter(match_phy,os.listdir(path)):
	    (target,lunid) = i.replace('phy-','').split(':')
	    tgt = "%s:0:0:%s" % (target,lunid)
            sysfs = SYSFS_PATH2
            for lun in os.listdir(sysfs):
                if not match_LUNs(lun,tgt):
                    continue
                dir = os.path.join(sysfs,lun,"device")
                for dev in filter(match_dev,os.listdir(dir)):
                    key = dev.replace("block:","")
                    entry = {}
                    entry['procname'] = proc
                    entry['host'] = id
                    entry['target'] = lun
                    devs[key] = entry

    dict['devs'] = devs
    dict['adt'] = adt
    return dict
            
def _getField(s):
    f = open(s, 'r')
    line = f.readline()[:-1]
    f.close()
    return line

def match_hbadevs(s, filterstr):
    regex = re.compile("^host[0-9]")
    if not regex.search(s, 0):
        return ""
    try:
        if os.path.exists(os.path.join(SYSFS_PATH1,s,"lpfc_fcp_class")):
            pname = "lpfc"
        else:
            filename = os.path.join(SYSFS_PATH1,s,"proc_name")
            pname = _getField(filename)
    except:
        return ""

    if filterstr == "any":
        for e in MODULE_INFO.iterkeys():
            regex = re.compile("^%s" % e)
            if regex.search(pname, 0):
                return pname
    else:
        regex = re.compile("^%s" % filterstr)
        if regex.search(pname, 0):
            return pname
    return ""

def match_rport(s):
    regex = re.compile("^rport-*")
    return regex.search(s, 0)

def match_targets(s):
    regex = re.compile("^target[0-9]")
    return regex.search(s, 0)

def match_phy(s):
    regex = re.compile("^phy-*")
    return regex.search(s, 0)

def match_LUNs(s, prefix):
    regex = re.compile("^%s" % prefix)
    return regex.search(s, 0)    

def match_dev(s):
    regex = re.compile("^block:")
    return regex.search(s, 0)

