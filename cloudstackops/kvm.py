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


class Kvm(hypervisor.hypervisor):

    def __init__(self, ssh_user='root', threads=5, pre_empty_script='', post_empty_script=''):
        hypervisor.__init__(ssh_user, threads)
        self.ssh_user = ssh_user
        self.threads = threads
        self.pre_empty_script = pre_empty_script
        self.post_empty_script = post_empty_script
        self.mountpoint = None

    def prepare_kvm(self, kvmhost):
        result = self.create_migration_nfs_dir(kvmhost)
        if self.DEBUG == 1:
            print "DEBUG: received this result:" + str(result)
        if result is False:
            print "Error: Could not prepare the migration folder on host " + kvmhost.name
            sys.exit(1)
        return True

    def find_nfs_mountpoint(self, host):
        print "Note: Looking for NFS mount on KVM host %s" % host.name
        if self.mountpoint is not None:
            print "Note: Found " + str(self.mountpoint)
            return self.mountpoint
        try:
            with settings(host_string=self.ssh_user + "@" + host.ipaddress):
                command = "sudo mount | grep storage | awk {'print $3'}"
                self.mountpoint = fab.run(command)
                print "Note: Found " + str(self.mountpoint)
                return self.mountpoint
        except:
            return False

    def get_migration_path(self):
        return self.mountpoint + "/migration/"

    def create_migration_nfs_dir(self, host):
        mountpoint = self.find_nfs_mountpoint(host)
        if len(mountpoint) == 0:
            print "Error: mountpoint cannot be empty"
            return False
        print "Note: Looking for migration folder"
        try:
            with settings(host_string=self.ssh_user + "@" + host.ipaddress):
                command = "sudo mkdir -p " + mountpoint + "/migration/"
                return fab.run(command)
        except:
            return False

    def download_volume(self, kvmhost, url, path):
        print "Note: Downloading disk from %s to host %s" % (url, kvmhost.name)
        try:
            with settings(host_string=self.ssh_user + "@" + kvmhost.ipaddress):
                command = "cd %s; sudo %s/download_volume.py -u %s -n %s.vhd" % \
                          (self.get_migration_path(), self.get_migration_path(), url, path)
                return fab.run(command)
        except:
            return False

    def make_kvm_compatible(self, kvmhost, path, skipvirtvtov=False, skippartitionfix=False):
        result = self.convert_volume_to_qcow(kvmhost, path)
        if result is False:
            print "Error: Could not convert volume %s on host %s" % (path, kvmhost.name)
            return False
        if skippartitionfix is False:
            result = self.fix_partition_size(kvmhost, path)
            if result is False:
                print "Error: Could not fix partition of volume %s on host %s" % (path, kvmhost.name)
                return False
        if skipvirtvtov is False:
            result = self.inject_drivers(kvmhost, path)
            if result is False:
                print "Error: Could not inject drivers on volume %s on host %s" % (path, kvmhost.name)
                return False
            result = self.move_datadisk_to_pool(kvmhost, path)
            if result is False:
                print "Error: Could not move rootvolume %s to the storage pool on host %s" % (path, kvmhost.name)
                return False
        else:
            result = self.move_rootdisk_to_pool(kvmhost, path)
            if result is False:
                print "Error: Could not move datavolume %s to the storage pool on host %s" % (path, kvmhost.name)
                return False
            print "Note: Skipping virt-v2v step due to --skipVirtvtov flag"
        return True

    def convert_volume_to_qcow(self, kvmhost, volume_uuid):
        print "Note: Converting disk %s to QCOW2 on host %s" % (volume_uuid, kvmhost.name)
        try:
            with settings(host_string=self.ssh_user + "@" + kvmhost.ipaddress):
                command = "cd %s; sudo qemu-img convert %s.vhd -O qcow2 %s" % (self.get_migration_path(),
                                                                             volume_uuid, volume_uuid)
                return fab.run(command)
        except:
            return False

    def fix_partition_size(self, kvmhost, volume_uuid):
        print "Note: Fixing disk %s to QCOW2 on host %s" % (volume_uuid, kvmhost.name)
        try:
            with settings(host_string=self.ssh_user + "@" + kvmhost.ipaddress):
                command = "cd %s; sudo qemu-img resize %s +500KB" % (self.get_migration_path(), volume_uuid)
                return fab.run(command)
        except:
            return False

    def inject_drivers(self, kvmhost, volume_uuid):
        print "Note: Inject drivers into disk %s on host %s" % (volume_uuid, kvmhost.name)
        try:
            with settings(host_string=self.ssh_user + "@" + kvmhost.ipaddress):
                command = "cd %s; sudo virt-v2v -i disk %s -o local -os ./" % (self.get_migration_path(), volume_uuid)
                return fab.run(command)
        except:
            return False

    def move_rootdisk_to_pool(self, kvmhost, volume_uuid):
        print "Note: Moving disk %s into place on host %s" % (volume_uuid, kvmhost.name)
        try:
            with settings(host_string=self.ssh_user + "@" + kvmhost.ipaddress):
                command = "cd %s; sudo mv %s-sda %s/%s" % (self.get_migration_path(), volume_uuid, self.mountpoint,
                                                           volume_uuid)
                return fab.run(command)
        except:
            return False

    def move_datadisk_to_pool(self, kvmhost, volume_uuid):
        print "Note: Moving disk %s into place on host %s" % (volume_uuid, kvmhost.name)
        try:
            with settings(host_string=self.ssh_user + "@" + kvmhost.ipaddress):
                command = "cd %s; sudo mv %s %s/%s" % (self.get_migration_path(), volume_uuid, self.mountpoint,
                                                           volume_uuid)
                return fab.run(command)
        except:
            return False

    def put_scripts(self, host):
        try:
            with settings(host_string=self.ssh_user + "@" + host.ipaddress):
                put('download_volume.py',
                    self.get_migration_path() + 'download_volume.py', mode=0755)
                if len(self.pre_empty_script) > 0:
                    put(self.pre_empty_script,
                        '/tmp/' + self.pre_empty_script.split('/')[-1], mode=0755)
                if len(self.post_empty_script) > 0:
                    put(self.post_empty_script,
                        '/tmp/' + self.post_empty_script.split('/')[-1], mode=0755)
            return True
        except:
            print "Warning: Could not upload check scripts to host " + host.name + ". Continuing anyway."
            return False
