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

# We depend on these
import socket
import sys
import time
import os

# Fabric
from fabric.api import *
from fabric import api as fab
from fabric import *

# Set user/passwd for fabric ssh
env.user = 'root'
env.password = 'password'
env.forward_agent = True
env.disable_known_hosts = True
env.parallel = False
env.pool_size = 1

# Supress Fabric output by default, we will enable when needed
output['debug'] = False
output['running'] = False
output['stdout'] = False
output['stdin'] = False
output['output'] = False
output['warnings'] = False


# Class to talk to hypervisors
class HypervisorMigration:

    def __init__(self):
        self.xenserver = None
        self.kvm = None
        self.sql = None

    def prepare_xenserver(self, xenhost):
        if not self.xenserver.create_migration_nfs_dir(xenhost):
            print "Error: Could not prepare the export folder on host " + xenhost
            sys.exit(1)
        return True

    def prepare_kvm(self, kvmhost):
        if not self.kvm.create_migration_nfs_dir(kvmhost):
            print "Error: Could not prepare the migration folder on host " + kvmhost
            sys.exit(1)
        return True

    def migrate_volume_from_xenserver_to_kvm(self, xshost, kvmhost, vdi_uuid):
        # Export volume
        if not self.xenserver.export_volume(xshost, vdi_uuid):
            print "Error: Could not export vdi %s on host %s" % (vdi_uuid, xshost)
            sys.exit(1)
        if not  self.kvm.download_volume_from_xenserver(xshost, kvmhost, vdi_uuid):
            print "Error: Could not download vdi %s from host %s to host %s" % (vdi_uuid, xshost, kvmhost)
            sys.exit(1)

