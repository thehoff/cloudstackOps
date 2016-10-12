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
import os.path
from random import choice
import getpass

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
    global skipVirtvtov
    skipVirtvtov = False

    # Usage message
    help = "Usage: ./" + os.path.basename(__file__) + ' [options] ' + \
        '\n  --config-profile -c <profilename>\tSpecify the CloudMonkey profile name to get the credentials from ' \
        '(or specify in ./config file)' + \
        '\n  --instance-name -i <instancename>\tMigrate VM with this instance name (i-123-12345-VM)' + \
        '\n  --tocluster -t <clustername>\t\tMigrate router to this cluster' + \
        '\n  --new-base-template -b <template>\tKVM template to link the VM to. Won\'t do much, mostly needed for ' \
        'properties like tags. We need to record it in the DB as it cannot be NULL and the XenServer one obviously ' \
        'doesn\'t work either.' + \
        '\n  --is-projectvm\t\t\tThis VMs belongs to a project' + \
        '\n  --mysqlserver -s <mysql hostname>\tSpecify MySQL server ' + \
        'to read HA worker table from' + \
        '\n  --mysqlpassword <passwd>\t\tSpecify password to cloud ' + \
        'MySQL user' + \
        '\n  --skip-virt-v2v\t\t\tSkipping the virt-v2v step' + \
        '\n  --debug\t\t\t\tEnable debug mode' + \
        '\n  --exec\t\t\t\tExecute for real'

    try:
        opts, args = getopt.getopt(
            argv, "hc:i:t:p:s:b:", [
                "config-profile=", "instance-name=", "tocluster=", "mysqlserver=", "mysqlpassword=",
                "new-base-template=", "skip-virt-v2v", "debug", "exec", "is-projectvm", "force"])
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
        elif opt in ("--skip-virt-v2v"):
            skipVirtvtov = True

    # Default to cloudmonkey default config file
    if len(configProfileName) == 0:
        configProfileName = "config"

    # We need at least these vars
    if len(instancename) == 0 or len(toCluster) == 0 or len(newBaseTemplate) == 0 or len(mysqlHost) == 0:
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

# Init XenServer class
x = xenserver.xenserver('root', threads)
c.xenserver = x

# Init KVM class
k = kvm.Kvm(getpass.getuser(), threads)
k.DEBUG = DEBUG
c.kvm = k

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

print "Note Cluster ID found for %s is %s" % (toCluster, toClusterID)

templateID = c.checkCloudStackName(
    {'csname': newBaseTemplate, 'csApiCall': 'listTemplates'})

print "Note Template ID found for %s is %s" % (newBaseTemplate, templateID)

if toClusterID == 1 or toClusterID is None:
    print "Error: Cluster with name '" + toCluster + "' can not be found! Halting!"
    sys.exit(1)

if templateID == 1 or templateID is None:
    print "Error: Template with name '" + newBaseTemplate + "' can not be found! Halting!"
    sys.exit(1)

# Get cluster hosts
cluster_hosts = c.getAllHostsFromCluster(toClusterID)
kvm_host = cluster_hosts[0]

# Select storage pool
targetStorageID = c.getRandomStoragePool(toClusterID)
targetStoragePoolData = c.getStoragePoolData(targetStorageID)
storagepooltags = targetStoragePoolData[0].tags
storagepoolname = targetStoragePoolData[0].name

# Get hosts that belong to toCluster
toClusterHostsData = c.getHostsFromCluster(toClusterID)
if DEBUG == 1:
    print "Note: You selected a storage pool with tags '" + str(storagepooltags) + "'"

# Get data from vm
vmdata = c.getVirtualmachineData(vmID)
if vmdata is None:
    print "Error: Could not find vm " + instancename + "!"
    sys.exit(1)

vm = vmdata[0]

if vm.hypervisor == "KVM":
    print "Error: VM %s aka '%s' is already happily running on KVM!" % (vm.instancename, vm.name)
    sys.exit(1)

if vm.state == "Running":
    needToStop = True
    autoStartVM = True
    print "Note: Found vm " + vm.name + " running on " + vm.hostname
else:
    print "Note: Found vm " + vm.name + " with state " + vm.state
    needToStop = False
    autoStartVM = False

# Volumes
voldata = c.getVirtualmachineVolumes(vmID, projectParam)
saved_storage_id = None
currentStorageID = None

# Get user data to e-mail
adminData = c.getDomainAdminUserData(vm.domainid)
if DRYRUN == 1:
    print "Note: Not sending notification e-mails due to DRYRUN setting. Would have e-mailed " + adminData.email
else:
    if not adminData.email:
        print "Warning: Skipping mailing due to missing e-mail address."

    templatefile = open(
        "email_template/migrateVirtualMachine_start.txt",
        "r")
    emailbody = templatefile.read()
    emailbody = emailbody.replace("FIRSTNAME", adminData.firstname)
    emailbody = emailbody.replace("LASTNAME", adminData.lastname)
    emailbody = emailbody.replace("DOMAIN", vm.domain)
    emailbody = emailbody.replace("VMNAME", vm.name)
    emailbody = emailbody.replace("STATE", vm.state)
    emailbody = emailbody.replace("INSTANCENAME", vm.instancename)
    emailbody = emailbody.replace("TOCLUSTER", toCluster)
    emailbody = emailbody.replace("ORGANIZATION", c.organization)
    templatefile.close()

    # Notify user
    msgSubject = 'Starting maintenance for VM ' + \
                 vm.name + ' / ' + vm.instancename
    c.sendMail(c.mail_from, adminData.email, msgSubject, emailbody)

    # Notify admin
    c.sendMail(c.mail_from, c.errors_to, msgSubject, emailbody)

    if DEBUG == 1:
        print emailbody

# Migrate its volumes
for vol in voldata:
    # Check if volume is already on correct storage
    currentStorageID = c.checkCloudStackName(
        {'csname': vol.storage, 'csApiCall': 'listStoragePools'})

    if saved_storage_id is None:
        saved_storage_id = currentStorageID

    if saved_storage_id != currentStorageID:
        print "Error: All attached volumes need to be on the same pool! (%s versus %s)" \
              % (saved_storage_id, currentStorageID)
        sys.exit(1)

    if currentStorageID == targetStorageID:
        print "Warning: No need to migrate volume " + vol.name + " -- already on the desired storage pool. Skipping."
        continue

if currentStorageID is None:
    print "Error: Unable to determine the current storage pool of the volumes."
    sys.exit(1)

# Figure out the tags
sodata = c.listServiceOfferings({'serviceofferingid': vm.serviceofferingid})
if sodata is not None:
    hosttags = (sodata[0].hosttags) if sodata[0].hosttags is not None else ''
    storagetags = (sodata[0].tags) if sodata[0].tags is not None else ''

    if storagetags == '':
        print "Warning: service offering has empty storage tags."

    if storagetags != '' and storagepooltags != storagetags and c.FORCE == 0:
        if DEBUG == 1:
            print "Error: cannot do this: storage tags from provided storage pool '" + storagepooltags + \
                  "' do not match your vm's service offering '" + storagetags + "'"
            sys.exit(1)
    elif storagetags != '' and storagepooltags != storagetags and c.FORCE == 1:
        if DEBUG == 1:
            print "Warning: storage tags from provided storage pool '" + storagepooltags + \
                  "' do not match your vm's service offering '" + storagetags + "'. Since you used --FORCE you " \
                  "probably know what you manually need to edit in the database."
    elif DEBUG == 1:
        print "Note: Storage tags look OK."

# Stop this vm if it was running
if needToStop:
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
            print "Error: " + result.virtualmachine.name + " is in state " + result.virtualmachine.state + \
                  " instead of Stopped. VM need to be stopped to continue. Re-run script to try again -- exit."

            # Notify admin
            msgSubject = 'Warning: problem with maintenance for VM ' + \
                         vm.name + ' / ' + vm.instancename
            emailbody = 'Could not stop VM ' + vm.name
            c.sendMail(c.mail_from, c.errors_to, msgSubject, emailbody)
            sys.exit(1)

# Here we have a stopped VM to work with

# Prepare the folders
k.prepare_kvm(kvm_host)
k.put_scripts(kvm_host)

# Get all volumes
volumes_result = s.get_volumes_for_instance(instancename)
for (name, path, uuid, vmstate, voltype) in volumes_result:
    print "Note: Processing volume '%s', filename '%s', uuid '%s'" % (name, path, uuid)

    if DRYRUN == 1:
        print "Would have extracted, downloaded, converted volume %s " % name
    else:
        if vmstate != "Stopped":
            print "Error: Volume %s is attached to a VM state %s (should be Stopped). Halting." % (name, vmstate)
            print "Note: Nothing has changed, you can either retry or start the VM on XenServer"
            sys.exit(1)

        # Transfer volume from XenServer to KVM
        print "Note: Extracting volume %s" % name
        url_to_download = c.extract_volume(uuid, vm.zoneid)
        if url_to_download is not None and len(url_to_download) == 0:
            print "Error: Transferring volume failed: did not get download url from API"
            print "Error: Check volume_store_ref table, field url. It should contain a valid URL or NULL"
            print "Note: Nothing has changed, you can either retry or start the VM on XenServer"
            sys.exit(1)
        if k.download_volume(kvm_host, url_to_download, path) is False:
            print "Error: Downloading volume failed"
            print "Note: Nothing has changed, you can either retry or start the VM on XenServer"
            sys.exit(1)
        print "Note: Downloading volume to KVM was successful"
        kvmresult = False
        if voltype == "DATADISK":
            print "Note: %s is a disk of type %s so skipping virt-v2v and friends" % (name, voltype)
            kvmresult = k.make_kvm_compatible(kvm_host, path, False, False)
        elif voltype == "ROOT":
            print "Note: %s is a disk of type %s" % (name, voltype)
            kvmresult = k.make_kvm_compatible(kvm_host, path, skipVirtvtov, True)
        else:
            print "Error: Found volume %s with unknown type %s. Halting." % (name, voltype)
            sys.exit(1)

        if kvmresult is False:
            print "Error: Making volume KVM compatible failed"
            print "Note: Nothing has changed, you can either retry or start the VM on XenServer"
            sys.exit(1)
        print "Note: Converting volume to KVM was successful"

print "Note: Updating the database"
if not s.update_instance_to_kvm(instancename, newBaseTemplate, storagepoolname):
    print "Error: Updating the database failed"
    print "Note: Nothing has changed, you can either retry or start the VM on XenServer"
    sys.exit(1)

# Start the VM again
if autoStartVM == "true":
    if DRYRUN == 1:
        print "Would have started vm " + vm.name + " with id " + vm.id + " on host " + toHostData.id
    else:
        print "Executing: start virtualmachine " + vm.name + " with id " + vm.id
        result = c.startVirtualMachine(vm.id)
        if result == 1:
            print "Start vm failed -- exiting."
            print "Error: investegate manually!"

            # Notify admin
            msgSubject = 'Warning: problem with maintenance for vm ' + \
                         vm.name + ' / ' + vm.instancename
            emailbody = "Could not start vm " + vm.name
            c.sendMail(c.mail_from, c.errors_to, msgSubject, emailbody)
            sys.exit(1)

        if result.virtualmachine.state == "Running":
            print "Note: " + result.virtualmachine.name + " is started successfully "
            # Get user data to e-mail
            adminData = c.getDomainAdminUserData(vm.domainid)
            if DRYRUN == 1:
                print "Note: Not sending notification e-mails due to DRYRUN setting. Would have e-mailed " + adminData.email
            else:

                if not adminData.email:
                    print "Warning: Skipping mailing due to missing e-mail address."

                templatefile = open(
                    "email_template/migrateVirtualMachine_done.txt",
                    "r")
                emailbody = templatefile.read()
                emailbody = emailbody.replace(
                    "FIRSTNAME",
                    adminData.firstname)
                emailbody = emailbody.replace(
                    "LASTNAME",
                    adminData.lastname)
                emailbody = emailbody.replace("DOMAIN", vm.domain)
                emailbody = emailbody.replace("VMNAME", vm.name)
                emailbody = emailbody.replace("STATE", vm.state)
                emailbody = emailbody.replace(
                    "INSTANCENAME",
                    vm.instancename)
                emailbody = emailbody.replace("TOCLUSTER", toCluster)
                emailbody = emailbody.replace(
                    "ORGANIZATION",
                    c.organization)
                templatefile.close()

                # Notify user
                msgSubject = 'Finished maintenance for VM ' + \
                             vm.name + ' / ' + vm.instancename
                c.sendMail(
                    c.mail_from,
                    adminData.email,
                    msgSubject,
                    emailbody)

                # Notify admin
                c.sendMail(c.mail_from, c.errors_to, msgSubject, emailbody)

                if DEBUG == 1:
                    print emailbody

        else:
            warningMsg = "Warning: " + result.virtualmachine.name + " is in state " + \
                         result.virtualmachine.state + \
                         " instead of Started. Please investigate (could just take some time)."
            print warningMsg
            autoStartVM = "false"

            # Notify admin
            msgSubject = 'Warning: problem with maintenance for VM ' + \
                         vm.name + ' / ' + vm.instancename
            emailbody = warningMsg
            c.sendMail(c.mail_from, c.errors_to, msgSubject, emailbody)

else:
    print "Warning: Not starting " + vm.name + " automatically!"
    # Get user data to e-mail
    adminData = c.getDomainAdminUserData(vm.domainid)
    if DRYRUN == 1:
        print "Note: Not sending notification e-mails due to DRYRUN setting. Would have e-mailed " + adminData.email
    else:

        if not adminData.email:
            print "Warning: Skipping mailing due to missing e-mail address."

        # Tell the user how to start the VM manually
        cloudmonkeyCmd = "cloudmonkey start virtualmachine id=" + vm.id

        templatefile = open(
            "email_template/migrateVirtualMachine_done_nostart.txt",
            "r")
        emailbody = templatefile.read()
        emailbody = emailbody.replace("FIRSTNAME", adminData.firstname)
        emailbody = emailbody.replace("LASTNAME", adminData.lastname)
        emailbody = emailbody.replace("DOMAIN", vm.domain)
        emailbody = emailbody.replace("VMNAME", vm.name)
        emailbody = emailbody.replace("STATE", vm.state)
        emailbody = emailbody.replace("INSTANCENAME", vm.instancename)
        emailbody = emailbody.replace("CLOUDMONKEYCMD", cloudmonkeyCmd)
        emailbody = emailbody.replace("TOCLUSTER", toCluster)
        emailbody = emailbody.replace("ORGANIZATION", c.organization)
        templatefile.close()

        # Notify user
        msgSubject = 'Finished maintenance for VM ' + \
                     vm.name + ' / ' + vm.instancename
        c.sendMail(c.mail_from, adminData.email, msgSubject, emailbody)

        # Notify mon-cloud
        c.sendMail(c.mail_from, c.errors_to, msgSubject, emailbody)

        if DEBUG == 1:
            print emailbody

# Disconnect MySQL
s.disconnectMySQL()
