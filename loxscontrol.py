# -*- coding: utf-8 -*-
"""NeuronModule Class for controlling a Loxone Homeautomation."""

import logging
import requests
from xml.etree import ElementTree
import pprint
import json
import tempfile
import re
from kalliope.core.NeuronModule import NeuronModule
from kalliope.core.NeuronModule import MissingParameterException, \
    InvalidParameterException

logging.basicConfig()
logger = logging.getLogger("kalliope")
logger.setLevel(logging.DEBUG)


class LoxSControl(NeuronModule):

    """NeuronModule Class for controlling a Loxone Homeautomation."""

    # Path definition
    STRUCTUREDEF = "/data/Loxapp3.json"
    VERSION = "/dev/sps/LoxAPPversion"
    SPSIO = "/dev/sps/io/"

    # Control elements used in Loxone
    TYPE_SWITCH = ["TimedSwitch", "Switch"]
    TYPE_LIGHTCONTROL = ["LightController"]
    TYPE_JALOUSIE = ["Jalousie"]

    # Categories used in Loxone
    CAT_LIGTH = "lights"
    CAT_JALOUSIE = "shading"
    CAT_UNDEF = "undefined"

    # Status Code Definitions
    # NameNotFound      - Name of Control Element not found in StructureDef
    # IncompleteRequest - Parameter is missing or not complete / consistent
    # Complete                 - Completed
    # StateChangeError  -  State of Control Element was not changed.
    #                                   Name not found, or changing failed
    STATUS_CODE_DEF = {"NameNotFound",
                       "IncompleteRequest",
                       "Complete",
                       "StateChangeError"
                       }

    def __init__(self, *args, **kwargs):
        """class init."""

        # call super init
        super(LoxSControl, self).__init__(*args, **kwargs)

        # get parameters from the neuron
        self._host = kwargs.get('lx_ip', None)
        self._user = kwargs.get('lx_user', None)
        self._password = kwargs.get('lx_password', None)
        self._controls = kwargs.get('lx_structuredef', None)

        self.change_room = kwargs.get('control_room', None)
        self.change_type = kwargs.get('control_type', None)
        self.change_name = kwargs.get('control_name', None)
        self.change_newstate = kwargs.get('newstate', None)

        # define request headers
        self._headers = {'accept': 'application/json'}

        # define output
        self.status_code = None

        # check if parameters have been provided
        if self._is_parameters_ok():

            # check provided args and do that
            if (self.change_name is not None) and \
                    (self.change_newstate is not None):
                if self.change_switch_state_byname(self.change_name,
                                                   self.change_newstate):
                    logger.debug(self.neuron_name +
                                 " State of %s changed to %s",
                                 self.change_name,
                                 self.change_newstate)
                    self.status_code = "Complete"
                else:
                    logger.debug(self.neuron_name +
                                 " State of %s not changed!",
                                 self.change_name)
                    self.status_code = "StateChangeError"

            if self.status_code is None:
                MissingParameterException(self.neuron_name +
                                          " needs more information to " +
                                          "process request.")
                self.status_code = "IncompleteRequest"

        else:
            self.status_code = "IncompleteRequest"

        # Finally say what I have done -> use a template
        self.message = {
            "status_code": self.status_code,
            "change_name": self.change_name,
            "change_newstate": self.change_newstate,
            "change_room": self.change_room,
        }
        self.say(self.message)

    def _is_parameters_ok(self):
        """
        Check if received parameters are ok to perform operations.

        :return: true if parameters are ok, raise an exception otherwise
        .. raises:: InvalidParameterException

        """
        # host ip is set
        if self._host is None:
            raise MissingParameterException(self.neuron_name +
                                            " needs a miniserver IP")

        # host user is set
        if self._user is None:
            raise MissingParameterException(self.neuron_name +
                                            " needs a miniserver user")

        # host password is set
        if self._password is None:
            raise MissingParameterException(
                self.neuron_name + " needs a miniserver user " +
                "password"
                )

        # load loxone config from miniserver
        if self._controls is None:
            if not self.load_config():
                raise MissingParameterException(
                    self.neuron_name + " can't load miniserver structure\
            definition"
                    )

        # enough information that I can do something?
        if (self.change_name is None) and (self.change_room is None) \
                and (self.change_type is None):
            raise MissingParameterException(self.neuron_name +
                                            " needs something to do")

        return True

    def change_switch_state_byuuid(self, controluuid,  newstate):
        """
        Change the state of a switch identified by controlname.

        :param controluuid: uuid of the control element
        :param newstate: new state of the switch
        :return: True if successful, False if not

        """

        logger.debug(self.neuron_name +
                     " Called Change State with %s UID and %s newstate",
                     controluuid,  newstate)
        print controluuid

        try:
            r = requests.get("http://"+self._host + self.SPSIO +
                             controluuid+"/"+newstate,
                             auth=(self._user, self._password))
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            logger.debug(self.neuron_name +
                         " Change switch state failed with response: %r",
                         r.text)
            return False
        except requests.exceptions.RequestException:
            logger.debug(self.neuron_name+" Change switch state failed.")
            return False

        logger.debug(self.neuron_name +
                     ' UID %s changed state to %s', controluuid, newstate)
# TODO: [Feature] check if state is correct -> analyse JSON answer
        return True

    def change_switch_state_byname(self, controlname,  newstate):
        """
        Change the state of a switch identified by controlname.

        :param controlname: name of the switch
        :param newstate: new state of the switch
        :return: True if successful, False if not

        """
        if self.get_uuid_by_name(controlname) is not None:
            return self.change_switch_state_byuuid(
                self.get_uuid_by_name(controlname), newstate)
        else:
            logger.debug(self.neuron_name +
                         ' Name %s not found in StructureDef', controlname)
            return False

    def get_uuid_by_name(self, controlname):
        """
        Return UUID identified by controlname.

        :param controlname: name of the switch
        :return: UUID of control in the structure definition
        or None if not found

        """
        for controlgroup in self._controls:
            subcontrol = self._controls[controlgroup]["controls"]
            for element in subcontrol:
                if subcontrol[element]["name"] in controlname:
                    return subcontrol[element]["uidAction"]
        return None

    def load_config(self):
        """
        Load the JSON Config File of the loxone miniserver.

        :return: true if config is loaded and parsed, false otherwise

        """
        # load structure definition
# TODO: [Feature] config should be cached and only loaded when needed
        try:
            r = requests.get("http://"+self._host +
                             self.STRUCTUREDEF, auth=(self._user,
                                                      self._password))
        except requests.ConnectionError:
            logger.debug(self.neuron_name +
                         ' Structure Definition Request failed.')
            return False

        try:
            r.raise_for_status()
            raw_info = r.json()['msInfo']
            raw_rooms = r.json()['rooms']
            raw_controls = r.json()['controls']
            raw_cats = r.json()['cats']
        except requests.exceptions.HTTPError:
            logger.debug(self.neuron_name +
                         ' Structure Definition Request failed with \
                response: %r',
                         r.text)
            return False
        except requests.exceptions.RequestException:
            logger.debug(self.neuron_name +
                         ' Structure Definition Request failed.')
            return False
        except ValueError as e:
            logger.debug(self.neuron_name +
                         ' Structure Definition cannot be parsed,\
                response: %s',
                         e.args[0])
            return False
        except KeyError:
            logger.debug(self.neuron_name +
                         ' Structure Definition cannot be parsed. KeyError.')
            return False

        # Parse structure
        try:
            # Get Info
            self._language = raw_info['languageCode']
            self._location = raw_info['location']
            self._roomtitle = raw_info['roomTitle']

            # Get rooms
            self._rooms = {}
            for room in raw_rooms:
                self._rooms[room] = {"name": raw_rooms[room]['name'],
                                     " uid": raw_rooms[room]['uuid']}

            # Get categories
            self._controls = {}
            for cat in raw_cats:
                self._controls[cat] = {"name": raw_cats[cat]['name'],
                                       " uid": raw_cats[cat]['uuid'],
                                       " type": raw_cats[cat]['type'],
                                       " controls": {}}

            # fill controls
            self.extract_controls(raw_controls)

        except KeyError:
            self._logger.critical(self.neuron_name +
                                ' Structure Definition cannot be parse. \
                 KeyError.'
                                  )
            return False
# TODO: FIX Language check
        # Check Language
        # try:
        #    language = self.profile['language']
        # except KeyError:
        #    language = 'en-US'
        # if language.split('-')[1]==self._language:
        #    raise ValueError("Home automation language is %s. But your
        # profile language is set to %s",self._language,language)

        # debug print
        pprint.pprint(self._controls)

        pprint.pprint(self._rooms)

        return True

    def extract_controls(self, jsonconfig):
        """
        Parse the given JSON and extract the control information.

        :param jsonconfig: controls block of the json file

        """
        # Step though each entry
        for control in jsonconfig:
                if jsonconfig[control]['type'] in self.TYPE_SWITCH:
                    self._controls[jsonconfig[control]['cat']][
                        'controls'][control] = {
                        "name": jsonconfig[control]['name'],
                        "uidAction": jsonconfig[control]['uuidAction'],
                        "room": jsonconfig[control]['room'],
                        "type": jsonconfig[control]['type']}
                elif jsonconfig[control]['type'] in self.TYPE_LIGHTCONTROL:
                        subcontrols = jsonconfig[control]['subControls']
                        for subcontrol in subcontrols:
                            if subcontrols[subcontrol]['type'] == "Switch":
                                self._controls[jsonconfig[control]['cat']][
                                    'controls'][subcontrol] = {
                                    "name": subcontrols[subcontrol]['name'],
                                    "uidAction": subcontrols[subcontrol][
                                        'uuidAction'],
                                    "room": jsonconfig[control]['room'],
                                    "type": subcontrols[subcontrol]['type']}
                elif jsonconfig[control]['type'] in self.TYPE_JALOUSIE:
                    self._controls[jsonconfig[control]['cat']][
                        'controls'][control] = {
                        "name": jsonconfig[control]['name'],
                        "uidAction": jsonconfig[control]['uuidAction'],
                        "room": jsonconfig[control]['room'],
                        "type": jsonconfig[control]['type']}

                # IRoomController
                # InfoOnlyAnalog
        return