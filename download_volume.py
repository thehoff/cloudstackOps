#!/usr/bin/python

#      Copyright 2016, Schuberg Philis BV
#
#      Licensed to the Apache Software Foundation (ASF) under one
#      or more contributor license agreements.  See the NOTICE file
#      distributed with this work for additional information
#      regarding copyright ownership.  The ASF licenses this file
#      to you under the Apache License, Version 2.0 (the
#      "License"); you may not use this file except in compliance
#      with the License.  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#      Unless required by applicable law or agreed to in writing,
#      software distributed under the License is distributed on an
#      "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#      KIND, either express or implied.  See the License for the
#      specific language governing permissions and limitations
#      under the License.

import requests
import os
import getopt
import sys


def handle_arguments(argv):
    global url_to_download
    url_to_download = ""

    global local_file_name
    local_file_name = ""

    # Usage message
    help = "Usage: ./" + os.path.basename(__file__) + ' [options] ' + \
           '\n -u --url\t\tThe url to download ' + \
           '\n -n --name\t\tThe name of the local file'

    try:
        opts, args = getopt.getopt(
            argv, "u:n:", ["url=", "name="])
    except getopt.GetoptError as e:
        print "Error: " + str(e)
        print help
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print help
            sys.exit()
        elif opt in ("-u", "--url"):
            url_to_download = arg
        elif opt in ("-n", "--name"):
            local_file_name = arg

    # We need at least these vars
    if len(url_to_download) == 0 or len(local_file_name) == 0:
        print help
        sys.exit()


def download_file(url, local_filename):
    print "Note: Downloading volume from %s to %s.." % (url, local_filename)
    try:
        r = requests.get(url, stream=True)
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk: # filter out keep-alive new chunks
                    f.write(chunk)
        return local_filename
    except:
        print "Note: Downloading failed!"
        return False

# Parse arguments
if __name__ == "__main__":
    handle_arguments(sys.argv[1:])

print "Note: Url is %s" % (str(url_to_download))

if len(url_to_download) > 0 and len(local_file_name) > 0:
    local_file = download_file(url_to_download, local_file_name)
    print "Note: Downloaded file %s to %s" % (url_to_download, local_file_name)
