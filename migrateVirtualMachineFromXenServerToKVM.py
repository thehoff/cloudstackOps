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

# Script to migrate a specific VM from XenServer to KVM
# Remi Bergsma - rbergsma@schubergphilis.com

import time
import sys
import getopt
from cloudstackops import cloudstackops
from cloudstackops import cloudstacksql
from cloudstackops import xenserver
from cloudstackops import kvm
from cloudstackops import hypervisormigration
import os.path
from random import choice

# Function to handle our arguments


def handleArguments(argv):
    global DEBUG
    DEBUG = 0
    global DRYRUN
    DRYRUN = 1
    global instancename
    instancename = ''
    global toCluster
    toCluster = ''
    global configProfileName
    configProfileName = ''
    global isProjectVm
    isProjectVm = 0
    global force
    force = 0
    global threads
    threads = 5
    global mysqlHost
    mysqlHost = ''
    global mysqlPasswd
    mysqlPasswd = ''
    global newBaseTemplate
    newBaseTemplate = ''

    # Usage message
    help = "Usage: ./" + os.path.basename(__file__) + ' [options] ' + \
        '\n  --config-profile -c <profilename>\tSpecify the CloudMonkey profile name to get the credentials from ' \
        '(or specify in ./config file)' + \
        '\n  --instance-name -i <instancename>\tMigrate VM with this instance name (i-123-12345-VM)' + \
        '\n  --tocluster -t <clustername>\t\tMigrate router to this cluster' + \
        '\n  --new-base-template -b <template>\t\tKVM template to link the VM to. Won\'t do much, mostly needed for ' \
        'properties like tags. We need to record it in the DB as it cannot be NULL and the XenServer one obviously ' \
        'doesn\'t work either.' + \
        '\n  --is-projectvm\t\t\tThis VMs belongs to a project' + \
        '\n  --mysqlserver -s <mysql hostname>\tSpecify MySQL server ' + \
        'to read HA worker table from' + \
        '\n  --mysqlpassword <passwd>\t\tSpecify password to cloud ' + \
        'MySQL user' + \
        '\n  --debug\t\t\t\tEnable debug mode' + \
        '\n  --exec\t\t\t\tExecute for real'

    try:
        opts, args = getopt.getopt(
            argv, "hc:i:t:p:s:b:", [
                "config-profile=", "instance-name=", "tocluster=", "mysqlserver=", "mysqlpassword=",
                "new-base-template=", "debug", "exec", "is-projectvm", "force"])
    except getopt.GetoptError as e:
        print "Error: " + str(e)
        print help
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print help
            sys.exit()
        elif opt in ("-c", "--config-profile"):
            configProfileName = arg
        elif opt in ("-i", "--instance-name"):
            instancename = arg
        elif opt in ("-t", "--tocluster"):
            toCluster = arg
        elif opt in ("-b", "--new-base-template"):
            newBaseTemplate = arg
        elif opt in ("-s", "--mysqlserver"):
            mysqlHost = arg
        elif opt in ("-p", "--mysqlpassword"):
            mysqlPasswd = arg
        elif opt in ("--debug"):
            DEBUG = 1
        elif opt in ("--exec"):
            DRYRUN = 0
        elif opt in ("--is-projectvm"):
            isProjectVm = 1
        elif opt in ("--force"):
            force = 1

    # Default to cloudmonkey default config file
    if len(configProfileName) == 0:
        configProfileName = "config"

    # We need at least these vars
    if len(instancename) == 0 or len(toCluster) == 0 or len(newBaseTemplate) == 0:
        print help
        sys.exit()

# Parse arguments
if __name__ == "__main__":
    handleArguments(sys.argv[1:])

if DEBUG == 1:
    print "Warning: Debug mode is enabled!"

if DRYRUN == 1:
    print "Warning: dry-run mode is enabled, not running any commands!"

# Init CloudStackOps class
c = cloudstackops.CloudStackOps(DEBUG, DRYRUN)

# Init Hypervisor Migration class
m = hypervisormigration.HypervisorMigration()

# Init XenServer class
x = xenserver.xenserver('root', threads)
m.xenserver = x

# Init KVM class
k = kvm.Kvm('root', threads)
m.kvm = k

# Init SQL class
s = cloudstacksql.CloudStackSQL(DEBUG, DRYRUN)

# Connect MySQL
result = s.connectMySQL(mysqlHost, mysqlPasswd)
if result > 0:
    print "Error: MySQL connection failed"
    sys.exit(1)
elif DEBUG == 1:
    print "DEBUG: MySQL connection successful"
    print s.conn

m.sql = s

# make credentials file known to our class
c.configProfileName = configProfileName

# Init the CloudStack API
c.initCloudStackAPI()

if DEBUG == 1:
    print "API address: " + c.apiurl
    print "ApiKey: " + c.apikey
    print "SecretKey: " + c.secretkey

# Check cloudstack IDs
if DEBUG == 1:
    print "Note: Checking CloudStack IDs of provided input.."

if isProjectVm == 1:
    projectParam = "true"
else:
    projectParam = "false"

vmID = c.checkCloudStackName({'csname': instancename,
                              'csApiCall': 'listVirtualMachines',
                              'listAll': 'true',
                              'isProjectVm': projectParam})
toClusterID = c.checkCloudStackName(
    {'csname': toCluster, 'csApiCall': 'listClusters'})

if toClusterID == 1 or toClusterID is None:
    print "Error: Cluster with name '" + toCluster + "' can not be found! Halting!"
    sys.exit(1)

# Get cluster hosts
cluster_hosts = c.getAllHostsFromCluster(toClusterID)
first_host = cluster_hosts[0]

# Select storage pool
targetStorageID = c.getRandomStoragePool(toClusterID)
targetStoragePoolData = c.getStoragePoolData(targetStorageID)
storagepooltags = targetStoragePoolData[0].tags

# Get hosts that belong to toCluster
toClusterHostsData = c.getHostsFromCluster(toClusterID)
if DEBUG == 1:
    print "Note: You selected a storage pool with tags '" + storagepooltags + "'"

# Get data from vm
vmdata = c.getVirtualmachineData(vmID)
if vmdata is None:
    print "Error: Could not find vm " + instancename + "!"
    sys.exit(1)

vm = vmdata[0]
if vm.state == "Running":
    needToStop = "true"
    autoStartVM = "true"
    print "Note: Found vm " + vm.name + " running on " + vm.hostname
else:
    print "Note: Found vm " + vm.name + " with state " + vm.state
    needToStop = "false"
    autoStartVM = "false"

# Figure out the tags
sodata = c.listServiceOfferings({'serviceofferingid': vm.serviceofferingid})
if sodata is not None:
    hosttags = (sodata[0].hosttags) if sodata[0].hosttags is not None else ''
    storagetags = (sodata[0].tags) if sodata[0].tags is not None else ''

    if storagetags == '':
        print "Warning: router service offering has empty storage tags."

    if storagetags != '' and storagepooltags != storagetags and c.FORCE == 0:
        if DEBUG == 1:
            print "Error: cannot do this: storage tags from provided storage pool '" + storagepooltags + "' do not match your vm's service offering '" + storagetags + "'"
            sys.exit(1)
    elif storagetags != '' and storagepooltags != storagetags and c.FORCE == 1:
        if DEBUG == 1:
            print "Warning: storage tags from provided storage pool '" + storagepooltags + "' do not match your vm's service offering '" + storagetags + "'. Since you used --FORCE you probably know what you manually need to edit in the database."
    elif DEBUG == 1:
        print "Note: Storage tags look OK."

# Stop this vm if it was running
if needToStop == "true":
    if DRYRUN == 1:
        print "Would have stopped vm " + vm.name + " with id " + vm.id
    else:
        print "Executing: stop virtualmachine " + vm.name + " with id " + vm.id
        result = c.stopVirtualMachine(vm.id)
        if result == 1:
            print "Stop vm failed -- exiting."
            print "Error: investegate manually!"

            # Notify admin
            msgSubject = 'Warning: problem with maintenance for vm ' + \
                         vm.name + ' / ' + vm.instancename
            emailbody = "Could not stop vm " + vm.name
            c.sendMail(c.mail_from, c.errors_to, msgSubject, emailbody)
            sys.exit(1)

        if result.virtualmachine.state == "Stopped":
            print "Note: " + result.virtualmachine.name + " is stopped successfully "
        else:
            print "Error: " + result.virtualmachine.name + " is in state " + result.virtualmachine.state + " instead of Stopped. VM need to be stopped to continue. Re-run script to try again -- exit."

            # Notify admin
            msgSubject = 'Warning: problem with maintenance for VM ' + \
                         vm.name + ' / ' + vm.instancename
            emailbody = 'Could not stop VM ' + vm.name
            c.sendMail(c.mail_from, c.errors_to, msgSubject, emailbody)
            sys.exit(1)

# Here we have a stopped VM to work with

# Prepare
m.prepare_xenserver(first_host)
m.prepare_kvm()

kvmhost = "TODO"

# Get all volumes
volumes_result = s.get_volumes_for_instance(instancename)
for (name, path) in volumes_result:
    m.migrate_volume_from_xenserver_to_kvm(first_host, kvmhost, path)

# Disconnect MySQL
s.disconnectMySQL()