#!/usr/bin/env python


# queue_manager.py
# Copyright 2012 Texas A&M University
# Joseph Rafferty
# jrafferty@tamu.edu
# 
# Script that is run at user login to install print queues.
#   Communicates with a web service to obtain a list of queues.
#   Deletes existing queues and installs queue received.

# How to use:
# 
# 1. Edit the server, post_uri, soap_action, header, and request_template class variables in the QueueRequest class to match the values for the web service you're using
# 2. Edit the printerModels class variable in the Printer class to add the printer models used in your organization.
# 3. Install this script on the client machine in a non-user writable location (/Library/Scripts/OAL/)
# 4. Set this script to run as a administrator-provided LaunchAgent (/Library/LaunchAgents) by creating your own plist or using the bundled template

import sys, os, platform
import httplib                      # to connect to our http SOAP service
from xml.dom import minidom         # to be able to read the service's response
from xml.sax.saxutils import escape # to properly escape our XML values
from subprocess import call, Popen, PIPE, STDOUT         # for the ability to use cmdline utilities to obtain system information
import signal
import commands
import re
import time
from datetime import datetime
import pickle

#######################################
# Logging stuff.
#######################################

# Change your log level here.
log_levels = ["error", "info", "debug"]
log_level = "debug"

def log(s, level="info"):
    if (log_levels.index(level) <= log_levels.index(log_level)):
        localtime = time.asctime( time.localtime(time.time()) )
        print s
        with open("/Library/Logs/OAL Queue Manager.log", "a") as f:
                    f.write(localtime+": "+s+"\n")
            
            
class SystemInfo:
    networkWaitTime = 0

    def __init__(self):
        pass

    def computerName(self):
        """Return the current computer name"""
        # Use scutil (System Configuration Utility) to query configd for our ComputerName
        return commands.getstatusoutput("scutil --get ComputerName")[1]
    
    def network_up(self):
        """Check for network up status"""
        try:
            p = Popen(['scutil'], stdout=PIPE, stdin=PIPE, stderr=STDOUT)
            stdout = p.communicate(input='open\nget State:/Network/Global/IPv4\nd.show\nquit\n')[0]
            primaryInt = re.search("PrimaryInterface : (.*)", stdout).group(1)
        except AttributeError, e:
            return False
        else:
            return True
            
    def userName(self):
        # Username was passed to us as argv[1]. For now, just use stat
        uname = commands.getstatusoutput("stat -f%Su /dev/console")[1]
        uname = re.search("([^@]*)", uname).group(1)
        return uname
    
    def osVersion(self):
        return platform.mac_ver()[0]
    
    def osMajorVersion(self):
        v = self.osVersion()
        return float('.'.join(v.split('.')[:2]))
        
sysInfo = SystemInfo()


class System:
    
    @classmethod
    def removeAllPrinters( cls ):
        printers = commands.getstatusoutput("lpstat -a | awk -F' ' '{print $1}'")[1]
        try:
            printers = printers.split('\n')
            for printer in printers:
                print "Deleting printer %s from the system" % printer
                if commands.getstatusoutput("lpadmin -x %s" % printer)[0] > 0:
                    raise Exception()
        except Exception as e:
            print "Error deleting printer %s from the system" % printer
        
        





#######################################
# Session is our parent class. It isn't intended to be instantiated directly.
# It contains most of the shared methods and attributes for our different session types
# Subclass this class for your other session types
#######################################

class QueueRequest(object):
    """Object to handle SOAP requests"""
    
    #######################################
    # Server information.
    #######################################
    server = "server"  # Server the webservice resides on
    postURI = "/printservices/printservices.asmx"  # URI that accepts the POST data
    soapAction = "http://server/PrintServices/GetPrintQueuesForWorkstation"  # SOAP Action header value
    headers = {
        'Host':server, 
        'Content-Type':'text/xml; charset=utf-8', 
        'SOAPAction':soapAction
    }  # Additional headers
    
    #######################################
    # XML template. % values will be replaced at the time of the request
    #######################################
    # request_template = """<?xml version="1.0" encoding="utf-8"?>
    # <soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    #   <soap:Body>
    #     <GetPrintQueuesForWorkstation xmlns="http://server/PrintServices/">
    #       <Key>thisisakeyforthemacs</Key>
    #       <ComputerName>%(computerName)s</ComputerName>
    #       <UserName>%(userName)s</UserName>
    #       <UserDomain>CONTINUUM</UserDomain>
    #       <Server></Server>
    #     </GetPrintQueuesForWorkstation>
    #   </soap:Body>
    # </soap:Envelope>"""
    
    requestTemplate = """<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        <GetPrintQueuesForWorkstation xmlns="http://server/PrintServices/">
          <Key>supersecretkey</Key>
          <ComputerName>SCC-100-001</ComputerName>
          <UserName>username</UserName>
          <UserDomain>DOMAIN</UserDomain>
          <Server></Server>
        </GetPrintQueuesForWorkstation>
      </soap:Body>
    </soap:Envelope>"""
    
    def __init__(self, computerName, userName):
        super(QueueRequest, self).__init__()
        self.computerName = computerName
        self.userName = userName
        
        if self.soap_request():
            self.parse_response()
        
    def soap_request(self):
        request = self.requestTemplate %  ( {'computerName':escape(self.computerName), 'userName':escape(self.userName) } )
        log("soap: mapped request variables", "debug")
        # Open connection to the service
        connection = httplib.HTTPConnection(self.server, 80)
        log("soap: opened connection to %s" %(self.server), "debug")
        # Send our request, complete with the headers and body, and save the response
        connection.request("POST", self.postURI, request, self.headers)
        log("soap: POSTed request to %s" %(self.postURI), "debug")
        log("soap: full headers: \n\t%s" %(self.headers), "debug")
        log("soap: full request: \n\t%s" %(request), "debug")
        
        response = connection.getresponse()
        
        responseString = response.read()
        log("soap: got response", "debug")
        self.responseDocument = minidom.parseString(responseString)
        log("soap: whole response: %s" % responseString, "debug")
        
        if response.status != 200:
            log("soap: Error code from the service manager: %d" % (response.status), "debug")
            if response.status == 500:
                log("soap: Detailed error message: %s" % document.getElementsByTagName("faultstring"), "debug")
            return False
        else:
            log("soap: 200 OK response", "debug")
            return True
            
    def parse_response(self):
        printersToMap = self.responseDocument.getElementsByTagName("PrintQueuesToMap")

        self.queues = []
        
        if printersToMap.length:
            for printQueue in printersToMap[0].childNodes:
                if printQueue.getElementsByTagName("Server").length:
                    server = printQueue.getElementsByTagName("Server")[0].childNodes[0].data.decode()
                if printQueue.getElementsByTagName("QueueShareName").length:
                    queue =  printQueue.getElementsByTagName("QueueShareName")[0].childNodes[0].data.decode()

                if (server is not None and queue is not None):
                    q = { 'server':server.strip(), 'queueName':queue.strip() }
                    self.queues.append(q)
                    
    def get_queues(self):
        return self.queues        

class Printer(object):
    
    # Add your printer models here
    # searchItems will be used in a case-insensitive match against the model string returned from the web service. All items must be found in the string.
    
    printerModels = {
        "Xerox 5550" : {
            "ppdName" : "Xerox Phaser 5550N.gz",
            "searchItems" : { "5550", "phaser", "xerox" }
        },
        "Xerox 4112" : {
            "ppdName" : "Xerox FreeFlow 4112 EPS Print Server.gz",
            "searchItems" : { "4112", "xerox" }
        },
        "Xerox 7760" : {
            "ppdName" : "Xerox Phaser 7760GX.gz",
            "searchItems" : { "7760", "phaser", "xerox" }
        },
        "HP Color LaserJet 5550" : {
            "ppdName" : "HP Color LaserJet 5550.gz",
            "searchItems" : { "5550", "hp", "color" }
        },
        "HP DesignJet 5500ps" : {
            "ppdName" : "HP Designjet 5500 PS3.gz",
            "searchItems" : { "5500", "hp", "designjet" }
        }
    }
    
    # Shouldn't have to edit these unless a path changes in a future OS release.
    
    genericDriverPath = "/System/Library/Frameworks/ApplicationServices.framework/Versions/A/Frameworks/PrintCore.framework/Versions/A/Resources/Generic.ppd"
    
    lionPrefix = "/Library/Printers/PPDs/Contents/Resources/"
    snowPrefix = "/Library/Printers/PPDs/"
    
    
    
    def __init__(self, queueData):
        super(Printer, self).__init__()
        self.queueData = queueData
        self.parseQueueData()
        self.ppdName = ""
        
    def parseQueueData(self):
        self.queueName = self.queueData["queueName"]
        self.server = self.queueData["server"]
        for k, model in self.printerModels.items():
            if self.queueData.get("modelName"):
                if self.parseModelName(model["searchItems"], self.queueData["modelName"]):
                    self.ppdName = model["searchItems"]
                    self.modelName = k
                

    def install(self):
        """docstring for install"""
        if self.ppdName:
            if sysInfo.osMajorVersion() > 10.6:
                ppdPath = os.path.join(self.lionPrefix, self.ppdPath)
            else:
                ppdPath = os.path.join(self.snowPrefix, self.ppdPath)
        else:
            ppdPath = self.genericDriverPath
            
        installString = "lpadmin -p %s -E -v smb://%s.domain/%s -P %s" % (self.queueName, self.server, self.queueName, ppdPath)
        print installString
        commands.getstatusoutput(installString)[1]
    
    def parseModelName(searchItems, modelName):
        found = True
        for item in searchItems:
            if not re.search(item, modelName, re.IGNORECASE):
                found = False
        return found

# Launchd requires that agents and daemons catch SIGTERM
def exit_handler(signum, frame):
    log("Caught a %s signal. Exiting." % sig)
    exit(1)
    
signal.signal(signal.SIGTERM, exit_handler)


#################
# Main program
#################

r = QueueRequest(sysInfo.computerName(), sysInfo.userName())
queues = r.get_queues()

# Delete all previously installed printers only if we got a new set of printers.
if len(queues):
    System.removeAllPrinters()

# Install the new set of printers
for queue in queues:
    print "Installing: %(server)s.domain/%(queueName)s" % (queue)
    p = Printer(queue)
    p.install()

