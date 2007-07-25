# Copyright (c) 2005-2006 XenSource, Inc. All use and distribution of this 
# copyrighted material is governed by and subject to terms and conditions 
# as licensed by XenSource, Inc. All other rights reserved.
# Xen, XenSource and XenEnterprise are either registered trademarks or 
# trademarks of XenSource Inc. in the United States and/or other countries.

###
# P2V TOOL
# HTTP PUT client functions
#
# Written by Andy Peace <andrew@xensource.con>

import httplib

def put(host, port, path, fobj, chunksize = 524288, https = False):
    """ Simple client-side put function.  Doesn't currently deal with redirects
    or authentication of any kind.  Returns the HTTP status code.  Does not
    read the body of the response. 
    
    host is target host.  port is target port.  path is target path. 
    fobj is an object that implements 'read'; provides data to be encoded and
    sent to server. """

    if https:
        conn = httplib.HTTPSConnection(host, port)
    else:
        conn = httplib.HTTPConnection(host, port)
    conn.putrequest("PUT", path)
    conn.putheader("Transfer-Encoding", "chunked")
    conn.putheader("Expect", "100-continue")
    conn.putheader("Accept", "*/*")
    conn.putheader("Connection", "close")
    conn.putheader("User-Agent", "XenSourceP2V/1.5")
    conn.endheaders()

    # now transfer the data:
    while True:
        data = fobj.read(chunksize)
        if data == "":
            break

        conn.send("%X\r\n" % len(data))
        conn.send(data + "\r\n")
    conn.send("0\r\n\r\n")

    r = conn.getresponse()
    conn.close()

    return r.status

