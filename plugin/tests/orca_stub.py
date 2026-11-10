"""A stand-in for OrcaSlicer's embedded `orca` module, enough to import and drive the plugin."""

import sys
import types


class PrinterAgentBase:
    config = "{}"

    def get_config(self):
        return self.config


class ScriptPluginCapabilityBase:
    pass


class AgentInfo:
    def __init__(self, id, name, version, description):
        self.id, self.name, self.version, self.description = id, name, version, description


DialogMode = types.SimpleNamespace(Orca="orca", Takeover="takeover")



class ExecutionResult:
    @staticmethod
    def success(message=""):
        return ("success", message)

    @staticmethod
    def skipped(message=""):
        return ("skipped", message)


class Preset:
    def __init__(self, name, values=None, is_system=False, file=""):
        self.name, self._values, self.is_system, self.file = name, values or {}, is_system, file

    def config_value(self, key):
        return self._values.get(key)

    def is_user(self):
        return not self.is_system and bool(self.file)


class Collection:
    def __init__(self, presets):
        self._presets = presets

    def size(self):
        return len(self._presets)

    def preset(self, i):
        return self._presets[i]


class Bundle:
    def __init__(self, current, printers=()):
        self._current = current
        self.printers = Collection(list(printers))
        self.filaments = Collection([])
        self.prints = Collection([])

    def current_printer_preset(self):
        return self._current


class Ui:
    WINDOW_MODAL = 1
    NotificationLevel = types.SimpleNamespace(RegularNotificationLevel="regular")

    def __init__(self):
        self.windows = []
        self.messages = []
        self.notifications = []

    def push_notification(self, level, text, hyper_text="", on_click=None):
        self.notifications.append((level, text, hyper_text, on_click))

    def create_window(self, **kwargs):
        self.windows.append(kwargs)
        return types.SimpleNamespace(post=lambda data: None, close=lambda: None, is_open=lambda: False)

    def message(self, text, title="OrcaSlicer", buttons="ok", icon="info"):
        self.messages.append(text)
        return "ok"


def install(bundle):
    orca = types.ModuleType("orca")
    printer_agent = types.ModuleType("orca.printer_agent")
    printer_agent.PrinterAgentBase = PrinterAgentBase
    printer_agent.AgentInfo = AgentInfo
    printer_agent.DialogMode = DialogMode
    orca.printer_agent = printer_agent
    orca.script = types.SimpleNamespace(ScriptPluginCapabilityBase=ScriptPluginCapabilityBase)
    orca.ExecutionResult = ExecutionResult
    orca.base = object
    orca.registered = []
    orca.plugin = lambda cls: cls
    orca.register_capability = orca.registered.append
    orca.permission_requests = []
    orca.request_permissions = lambda **kwargs: orca.permission_requests.append(kwargs)
    orca.reloaded = []
    bundles = types.SimpleNamespace(reload_local=orca.reloaded.append)
    orca.host = types.SimpleNamespace(preset_bundle=lambda: bundle, ui=Ui(), preset=types.SimpleNamespace(bundles=bundles))
    sys.modules["orca"] = orca
    sys.modules["orca.printer_agent"] = printer_agent
    return orca
