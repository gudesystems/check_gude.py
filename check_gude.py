#!/usr/bin/python

import argparse
import requests
import json
import fnmatch

parser = argparse.ArgumentParser(prog='check_gude')
parser.add_argument('-H', '--host', help='ip address of target host')
parser.add_argument('-s', '--ssl', help='use https connection', action="store_true")
parser.add_argument('--username', help='username for HTTP basic auth credentials')
parser.add_argument('--password', help='password for HTTP basic auth credemtials')
parser.add_argument('--sensor', help='')
parser.add_argument('--numeric', help='', action="store_true", default=False)
parser.add_argument('--nagios', help='', action="store_true", default=False)
parser.add_argument('-w', '--warning', help='nagios: threshold to exit as warning level', default=0.0)
parser.add_argument('-c', '--critical', help='nagios: threshold to exit as critical level', default=0.0)
parser.add_argument('--operator', help='nagios: check warn/crit levels by one of >,<,>=,<=', default=">")
parser.add_argument('--label', help='nagios: sensor label', default="sensor")
parser.add_argument('--unit', help='nagios: sensor label', default="")

args = parser.parse_args()

EXIT_OK = 0
EXIT_WARNING = 1
EXIT_ERROR = 2


class GudeSensor:
    values = {}

    #
    # get sensor_desc / sensor_values as JSON objects
    #
    def getSensorsJson(self, host, ssl, username=None, password=None):
        if ssl:
            url = 'https://'
        else:
            url = 'http://'

        url += host + '/' + 'status.json'

        auth = None
        if username:
            auth = requests.auth.HTTPBasicAuth(username, password)

        r = requests.get(url, params={'components': 0x14000}, verify=False, auth=auth)

        if r.status_code == 200:
            return json.loads(r.text)
        else:
            raise ValueError("http request error {0}".format(r.status))

    #
    # check nagios limits
    #
    def checkThreshExceeded(self, value, thresh, operator):
        if operator == '<' and float(value) < float(thresh):
            return True
        if operator == '>' and float(value) > float(thresh):
            return True
        if operator == '<=' and float(value) <= float(thresh):
            return True
        if operator == '>=' and float(value) >= float(thresh):
            return True
        return False

    #
    # print nagios status text
    #
    def nagiosText(self, level, value, labelindex):
        return ("{0}: {1}={2}{3} (w: {4}, c: {5}, op:{6})".format(
            level, self.label + labelindex, value, self.unit, self.warning, self.critical, self.operator))

    #
    # set nagios exit code to most critical item
    #
    def setExitCode(self, exitcode, level):
        if level > exitcode:
            exitcode = level

    #
    # store sensor-field as dict identified by locatorStr
    #
    def store(self, locatorStr, value, fieldProp, prefix=""):
        field = {
            'value': value,
            'unit': fieldProp["unit"],
            'name': fieldProp["name"]
        }
        self.values[locatorStr] = field
        if not self.filter:
            print("{0}{1} {2} {3} {4}".format(prefix, locatorStr, field["value"], fieldProp["unit"], fieldProp["name"]))
        return field

    #
    # print Sensor id / name
    #
    def printSensorIdStr(self, sensorProp, prefix=""):
        if not self.filter:
            print("{0}{1} {2}".format(prefix, sensorProp["id"], sensorProp["name"]))

    #
    # walk and merge sensor_decr/sensor_value
    #
    def collectSensorData(self):
        jsonIndex = -1
        for sensorType in self.sensorJson["sensor_descr"]:
            jsonIndex += 1
            sensorValues = self.sensorJson["sensor_values"][jsonIndex]["values"]
            st = sensorType["type"]

            for (si, sensorProp) in enumerate(sensorType["properties"]):
                self.printSensorIdStr(sensorProp)

                # simple ungrouped sensors
                if 'fields' in sensorType:
                    for (sf, fieldProp) in enumerate(sensorType["fields"]):
                        field = self.store("{0}.{1}.{2}".format(st, si, sf),
                                           sensorValues[si][sf]["v"],
                                           fieldProp, "\t")

                # complex sensor groups
                if 'groups' in sensorType:
                    for (gi, sensorGroup) in enumerate(sensorProp["groups"]):
                        for (grm, groupMember) in enumerate(sensorGroup):
                            self.printSensorIdStr(groupMember, "\t")
                            for (sf, fieldProp) in enumerate(sensorType["groups"][gi]["fields"]):
                                field = self.store("{0}.{1}.{2}.{3}.{4}".format(st, si, gi, grm, sf),
                                                   sensorValues[si][gi][grm][sf]["v"],
                                                   fieldProp, "\t\t")

    #
    # print all requestes sensors
    #
    def printSensorInfo(self, label, unit, numeric, nagios, critical, warning, operator):
        maxexitcode = 0
        labelindex = 0
        self.label = label
        self.unit = unit
        self.warning = warning
        self.critical = critical
        self.operator = operator

        nagiosPerfomanceText = "";
        if self.filter:
            for sensor in gudeSensors.values:
                if fnmatch.fnmatch(sensor, self.filter):
                    if nagios:
                        exitcode = 0
                        labelindex += 1

                        if not exitcode and self.checkThreshExceeded(self.values[sensor]["value"], critical, operator):
                            print(self.nagiosText("CRITICAL", self.values[sensor]["value"], str(labelindex)))
                            exitcode = 2

                        if not exitcode and self.checkThreshExceeded(self.values[sensor]["value"], warning, operator):
                            print(self.nagiosText("WARNING", self.values[sensor]["value"], str(labelindex)))
                            exitcode = 1

                        if not exitcode:
                            print(self.nagiosText("OK", self.values[sensor]["value"], str(labelindex)))

                        if maxexitcode < exitcode:
                            maxexitcode = exitcode

                        nagiosPerfomanceText += " {0}{1}={2}{3};{4};{5}".format(label, labelindex, self.values[sensor]["value"], unit, warning, critical)
                    else:
                        if not numeric:
                            print("{0} {1} {2} {3}".format(sensor, self.values[sensor]["name"],
                                                           self.values[sensor]["value"],
                                                           self.values[sensor]["unit"]))
                        else:
                            print("{0}".format(self.values[sensor]["value"]))

        if nagios and nagiosPerfomanceText:
            print("{0} |{1}".format(self.host, nagiosPerfomanceText))

        self.exitcode = maxexitcode

    def __init__(self, host, filter, ssl, username, password):
        self.filter = filter
        self.host = host
        self.sensorJson = self.getSensorsJson(host, ssl, username, password)
        self.collectSensorData()


try:
    gudeSensors = GudeSensor(str(args.host), args.sensor, args.ssl, args.username, args.password)
except:
    print("ERROR getting sensor json")
    exit(EXIT_ERROR)

gudeSensors.printSensorInfo(args.label, args.unit, args.numeric, args.nagios, args.critical, args.warning,
                            args.operator)
exit(gudeSensors.exitcode)