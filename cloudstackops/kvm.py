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
import hypervisor

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


class Kvm(hypervisor):

    def __init__(self, ssh_user='root', threads=5):
        self.ssh_user = ssh_user
        self.threads = threads
        self.mountpoint = ""

    def prepare_kvm(self, kvmhost):
        result = self.create_migration_nfs_dir(kvmhost)
        if not result:
            print "Error: Could not prepare the migration folder on host " + kvmhost
            sys.exit(1)
        print "Note received this result:" + str(result)
        return True

    def find_nfs_mountpoint(self, host):
        print "Note: Looking for NFS mount on KVM"
        if self.mountpoint is not None:
            return self.mountpoint
        try:
            with settings(host_string=self.ssh_user + "@" + host.ipaddress):
                command = "mount | grep storage | awk {'print $3'}"
                self.mountpoint = fab.run(command)
                print "Note: Found " + str(self.mountpoint)
                return self.mountpoint
        except:
            return False

    def get_migration_path(self):
        return self.mountpoint + "migration/"

    def create_migration_nfs_dir(self, host):
        self.find_nfs_mountpoint(host)
        print "Note: Looking for migration folder"
        try:
            with settings(host_string=self.ssh_user + "@" + host.ipaddress):
                command = "mkdir -p " + self.mountpoint
                return fab.run(command)
        except:
            return False

    def download_volume_from_xenserver(self, xenhost, kvmhost, vdi_uuid):
        print "Note: Downloading disk %s from %s to %s" % (vdi_uuid, xenhost, kvmhost)
        try:
            with settings(host_string=self.ssh_user + "@" + kvmhost.ipaddress):
                command = "cd %s; wget http://%s:50000/%s.vhd" % (self.get_migration_path(), xenhost, vdi_uuid)
                return fab.run(command)
        except:
            return False

    def make_kvm_compatible(self, kvmhost, volume_uuid):
        result = self.convert_volume_to_qcow(kvmhost, volume_uuid)
        if not result:
            print "Error: Could not convert volume %s on host %s" % (volume_uuid, kvmhost)
            return False
        result = self.fix_partition_size(kvmhost, volume_uuid)
        if not result:
            print "Error: Could not fix partition of volume %s on host %s" % (volume_uuid, kvmhost)
            return False
        result = self.inject_drivers(kvmhost, volume_uuid)
        if not result:
            print "Error: Could not inject drivers on volume %s on host %s" % (volume_uuid, kvmhost)
            return False
        result = self.move_disk_to_pool(kvmhost, volume_uuid)
        if not result:
            print "Error: Could not move volume %s to the storage pool on host %s" % (volume_uuid, kvmhost)
            return False
        return True

    def convert_volume_to_qcow(self, kvmhost, volume_uuid):
        print "Note: Converting disk %s to QCOW2 on host %s" % (volume_uuid, kvmhost)
        try:
            with settings(host_string=self.ssh_user + "@" + kvmhost.ipaddress):
                command = "cd %s; qemu-img convert %s.vhd -O qcow2 -c %s" % (self.get_migration_path(),
                                                                             volume_uuid, volume_uuid)
                return fab.run(command)
        except:
            return False

    def fix_partition_size(self, kvmhost, volume_uuid):
        print "Note: Fixing disk %s to QCOW2 on host %s" % (volume_uuid, kvmhost)
        try:
            with settings(host_string=self.ssh_user + "@" + kvmhost.ipaddress):
                command = "cd %s; qemu-img resize %s +500KB" % (self.get_migration_path(), volume_uuid)
                return fab.run(command)
        except:
            return False

    def inject_drivers(self, kvmhost, volume_uuid):
        print "Note: Inject drivers into disk %s on host %s" % (volume_uuid, kvmhost)
        try:
            with settings(host_string=self.ssh_user + "@" + kvmhost.ipaddress):
                command = "cd %s; virt-v2v -i disk %s -o local -os ./" % (self.get_migration_path(), volume_uuid)
                return fab.run(command)
        except:
            return False

    def move_disk_to_pool(self, kvmhost, volume_uuid):
        print "Note: Moving disk %s into place on host %s" % (vdi_uuid, kvmhost)
        try:
            with settings(host_string=self.ssh_user + "@" + kvmhost.ipaddress):
                command = "cd %s; mv %s-sda %s/%s" % (self.get_migration_path(), volume_uuid, self.mountpoint,
                                                      volume_uuid)
                return fab.run(command)
        except:
            return False
