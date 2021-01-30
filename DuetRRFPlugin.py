import json

from PyQt5.QtCore import Qt, QTimer

from cura.CuraApplication import CuraApplication
from cura.Settings.CuraContainerRegistry import CuraContainerRegistry

from UM.Message import Message
from UM.Logger import Logger
from UM.Extension import Extension
from UM.OutputDevice.OutputDevicePlugin import OutputDevicePlugin
from UM.i18n import i18nCatalog

catalog = i18nCatalog("cura")

from .DuetRRFOutputDevice import DuetRRFConfigureOutputDevice, DuetRRFOutputDevice, DuetRRFDeviceType
from .DuetRRFSettings import delete_config, get_config, init_settings, DUETRRF_SETTINGS


class DuetRRFPlugin(Extension, OutputDevicePlugin):
    def __init__(self):
        super().__init__()
        self._application = CuraApplication.getInstance()
        self._application.globalContainerStackChanged.connect(self._checkDuetRRFOutputDevices)
        self._application.initializationFinished.connect(self._delay_check_unmapped_settings)

        init_settings()

        self.addMenuItem(catalog.i18n("(moved to Preferences→Printer)"), self._showUnmappedSettingsMessage)

        self._found_unmapped = {}

    def start(self):
        pass

    def stop(self, store_data: bool = True):
        pass

    def _delay_check_unmapped_settings(self):
        self._change_timer = QTimer()
        self._change_timer.setInterval(10000)
        self._change_timer.setSingleShot(True)
        self._change_timer.timeout.connect(self._check_unmapped_settings)
        self._change_timer.start()

    def _check_unmapped_settings(self):
        Logger.log("d", "called")
        try:
            instances = json.loads(self._application.getPreferences().getValue(DUETRRF_SETTINGS))

            stacks = CuraContainerRegistry.getInstance().findContainerStacks(type='machine')
            stacks = [stack.getId() for stack in stacks]

            for printer_id, data in instances.items():
                if printer_id not in stacks:
                    self._found_unmapped[printer_id] = data
        except Exception as e:
            Logger.log("d", str(e))

        if self._found_unmapped:
            Logger.log("d", "Unmapped settings found!")
            self._showUnmappedSettingsMessage()
        else:
            Logger.log("d", "No unmapped settings found.")

    def _showUnmappedSettingsMessage(self):
        Logger.log("d", "called: {}".format(self._found_unmapped.keys()))

        msg = (
            "Settings for the DuetRRF plugin moved to the Printer preferences.\n\n"
            "Please go to:\n"
            "→ Cura Preferences\n"
            "→ Printers\n"
            "→ activate and select your printer\n"
            "→ click on 'Connect Duet RepRapFirmware'\n"
        )
        if self._found_unmapped:
            msg += "\n\n"
            msg += "You have unmapped settings for unknown printers:\n"
            for printer_id, data in self._found_unmapped.items():
                t = "   {}:\n".format(printer_id)
                if "url" in data and data["url"].strip():
                    t += "→ URL: {}\n".format(data["url"])
                if "duet_password" in data and data["duet_password"].strip():
                    t += "→ Duet password: {}\n".format(data["duet_password"])
                if "http_username" in data and data["http_username"].strip():
                    t += "→ HTTP Basic username: {}\n".format(data["http_username"])
                if "http_password" in data and data["http_password"].strip():
                    t += "→ HTTP Basic password: {}\n".format(data["http_password"])
                msg += t

        message = Message(
            msg,
            lifetime=0,
            title="DuetRRF: Settings moved to Cura Preferences!",
        )
        if self._found_unmapped:
            message.addAction(
                action_id="ignore",
                name=catalog.i18nc("@action:button", "Ignore"),
                icon="",
                description="Close this message",
            )
            message.addAction(
                action_id="delete",
                name=catalog.i18nc("@action:button", "Delete"),
                icon="",
                description="Delete unmapped settings for unknown printers",
            )
            message.actionTriggered.connect(self._onActionTriggeredUnmappedSettings)
        message.show()

    def _onActionTriggeredUnmappedSettings(self, message, action):
        Logger.log("d", "called: {}, {}".format(action, self._found_unmapped.keys()))
        message.hide()

        if action == "ignore":
            return
        if action == "delete" and not self._found_unmapped:
            return

        for printer_id in self._found_unmapped.keys():
            if delete_config(printer_id):
                Logger.log("d", "successfully delete unmapped settings for {}".format(printer_id))
            else:
                Logger.log("e", "failed to delete unmapped settings for {}".format(printer_id))

        message = Message(
            "Unmapped settings have been deleted for the following printers:\n{}\n\n".format(
                ",\n".join(self._found_unmapped.keys())
            ),
            lifetime=5000,
            title="DuetRRF: unmapped settings successfully deleted!",
        )
        message.show()
        self._found_unmapped = {}

    def _checkDuetRRFOutputDevices(self):
        global_container_stack = self._application.getGlobalContainerStack()
        if not global_container_stack:
            return

        manager = self.getOutputDeviceManager()

        # remove all DuetRRF output devices - the new stack might not need them or have a different config
        manager.removeOutputDevice("duetrrf-configure")
        manager.removeOutputDevice("duetrrf-print")
        manager.removeOutputDevice("duetrrf-simulate")
        manager.removeOutputDevice("duetrrf-upload")

        # check and load new output devices
        s = get_config()
        if s:
            Logger.log("d", "DuetRRF is active for printer: id:{}, name:{}".format(
                global_container_stack.getId(),
                global_container_stack.getName(),
            ))
            manager.addOutputDevice(DuetRRFOutputDevice(s, DuetRRFDeviceType.print))
            manager.addOutputDevice(DuetRRFOutputDevice(s, DuetRRFDeviceType.simulate))
            manager.addOutputDevice(DuetRRFOutputDevice(s, DuetRRFDeviceType.upload))
        else:
            manager.addOutputDevice(DuetRRFConfigureOutputDevice())
            Logger.log("d", "DuetRRF is not available for printer: id:{}, name:{}".format(
                global_container_stack.getId(),
                global_container_stack.getName(),
            ))
