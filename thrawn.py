import sys
import os
import logging
import json
from Xlib import X, XK, display
from Xlib.ext import record
from Xlib.protocol import rq
from PyQt5.QtCore import Qt, QThread
from PyQt5.QtWidgets import QApplication, QWidget, QDesktopWidget, QLineEdit
from PyQt5.QtWidgets import QLabel


class ThrawnConfig:
    def __init__(self):
        self.tconfig_map = {}
        self.tconfig_load()

    def tconfig_save_default(self):
        self.tconfig_map = {'Terminal': 'xfce4-terminal',
                            'Terminal exec option flag': '-x',
                            'Height': 24,
                            'Focus keys': ['Control_L', 'Shift_L']}
        self.tconfig_save()

    @property
    def focus_keymap(self):
        return self.tconfig_map['Focus keys']

    @focus_keymap.setter
    def focus_keymap(self, focus_keymap):
        self.tconfig_map['Focus keys'] = focus_keymap
        self.tconfig_save()

    @property
    def terminal(self):
        return self.tconfig_map['Terminal']

    @terminal.setter
    def terminal(self, terminal):
        self.tconfig_map['Terminal'] = terminal
        self.tconfig_save()

    @property
    def terminal_exec_flag(self):
        return self.tconfig_map['Terminal exec option flag']

    @terminal_exec_flag.setter
    def terminal_exec_flag(self, terminal_exec_flag):
        self.tconfig_map['Terminal exec option flag'] = terminal_exec_flag
        self.tconfig_save()

    @property
    def height(self):
        return self.tconfig_map['Height']

    @height.setter
    def height(self, height):
        self.tconfig_map['Height'] = height
        self.tconfig_save()

    def tconfig_save(self):
        tconfig_path = self.get_tconfig_path()
        tconfig_path += '/thrawn/thrawn.conf'
        self.dir_check(os.path.dirname(tconfig_path))
        with open(tconfig_path, 'w') as f:
            json.dump(self.tconfig_map, f)

    def tconfig_load(self):
        tconfig_path = self.get_tconfig_path()
        try:
            with open(tconfig_path + '/thrawn/thrawn.conf') as f:
                self.tconfig_map = json.load(f)
        except FileNotFoundError:
            logging.warning('configuration file not found, \
                             writing a default one')
            self.tconfig_save_default()

    def dir_check(self, directory):
        if not os.path.exists(directory):
            os.makedirs(directory)

    def get_tconfig_path(self):
        xdg_home = os.getenv('XDG_tconfig_HOME')
        if xdg_home:
            tconfig_path = xdg_home
        else:
            home = os.getenv('HOME')
            if not home:
                logging.critical('HOME variable not defined')
                sys.exit(1)
            else:
                tconfig_path = home + '/.tconfig'
        return tconfig_path


# FROM https://gist.github.com/whym/402801#file-keylogger-py
class XInputThread(QThread):
    def __init__(self, panel, tconfig):
        QThread.__init__(self)
        self.local_dpy = display.Display()
        self.record_dpy = display.Display()
        self.tconfig = tconfig
        self.panel = panel
        self.keymap = self.tconfig.focus_keymap
        self.received_keys = list()

    def lookup_keysym(self, keysym):
        for name in dir(XK):
            if name[:3] == "XK_" and getattr(XK, name) == keysym:
                return name[3:]
        return '[{key}]'.format(key=keysym)

    def record_callback(self, reply):
        if reply.category != record.FromServer:
            return
        elif reply.client_swapped:
            logging.warning("Received swapped protocol data, cowardly ignored")
            return
        elif not len(reply.data) or ord(str(reply.data[0])) < 2:
            # not an event
            return

        data = reply.data
        while len(data):
            event, data = rq.EventField(None).parse_binary_value(
                    data, self.record_dpy.display, None, None)
            if event.type in [X.KeyPress, X.KeyRelease]:
                keysym = self.local_dpy.keycode_to_keysym(event.detail, 0)
                if keysym:
                    received_key = self.lookup_keysym(keysym)
                    if received_key in self.keymap :
                        if received_key not in self.received_keys:
                            self.received_keys.append(received_key)
                            if len(self.received_keys) == 2:
                                self.panel.activateWindow()
                                self.received_keys.clear()

    def run(self):
        # Check if the extension is present
        if not self.record_dpy.has_extension("RECORD"):
            logging.critical("RECORD extension not found")
            sys.exit(1)

        # Create a recording context; we only want key and mouse events
        ctx = self.record_dpy.record_create_context(
                0,
                [record.AllClients],
                [{
                    'core_requests': (0, 0),
                    'core_replies': (0, 0),
                    'ext_requests': (0, 0, 0, 0),
                    'ext_replies': (0, 0, 0, 0),
                    'delivered_events': (0, 0),
                    'device_events': (X.KeyPress, X.KeyPress),
                    'errors': (0, 0),
                    'client_started': False,
                    'client_died': False
                }])

        # Enable the context; this only returns after
        # a call to record_disable_context,
        # while calling the callback function in the meantime
        self.record_dpy.record_enable_context(ctx, self.record_callback)

        # Finally free the context
        self.record_dpy.record_free_context(ctx)

        self.exec_()


class Panel(QWidget):
    def __init__(self, tconfig):
        super().__init__()
        self.tconfig = tconfig
        self.init_ui()
        self.x_input_thread = XInputThread(self, tconfig)
        self.x_input_thread.start()

    def init_ui(self):
        screen = QDesktopWidget().availableGeometry()
        self.resize(screen.width(), self.tconfig.height)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.move(0, 0)

        command_label = CommandsLabel(self, self.tconfig)

        command_line_edit = CommandLineEdit(self, command_label,
                                            self.tconfig)


class BuiltInCommands:
    @staticmethod
    def built_in_commands_dict():
        built_in_commands = {}
        met_names = list((el for el in BuiltInCommands.__dict__ if
                          el.find('__') and el.find('built_in_commands_dict')))
        for el in met_names:
            built_in_commands[el] = 'BuiltInCommands.' + el + '()'
        return built_in_commands

    @staticmethod
    def thrawn_quit():
        sys.exit(0)


class CommandLineEdit(QLineEdit):
    def __init__(self, parent, command_label, tconfig):
        super().__init__(parent)
        self.tconfig = tconfig
        self.command_label = command_label
        self.exec_list = self.get_exec_list()
        self.init_ui()
        self.init_signals()

    def init_ui(self):
        self.resize(300, self.tconfig.height)
        self.move(0, 0)
        self.setFocus(Qt.OtherFocusReason)

    def init_signals(self):
        self.returnPressed.connect(self.command_choose)
        self.textChanged.connect(self.change_command_label_text)

    def command_choose(self):
        completion_list = self.get_completion()
        if self.text() in completion_list:
            self.command_run(self.text())
        else:
            self.command_run(completion_list[0])

    def command_run(self, command):
        os.popen(self.tconfig.terminal + ' ' +
                 self.tconfig.terminal_exec_flag + ' ' +
                 command)

    def get_exec_list(self):
        exec_list = []
        path = os.getenv('PATH')
        if path:
            list_dir = path.split(':')
            for directory in list_dir:
                for _, _, list_file in os.walk(directory):
                    exec_list += list_file
        else:
            logging.critical('PATH environment variable not set')
            sys.exit(1)
        return exec_list

    def get_completion(self):
        match_list = []
        if self.text():
            match_list.extend(el for el in self.exec_list if self.text() in el)
        return match_list

    def change_command_label_text(self):
        completion_list = self.get_completion()
        self.command_label.setText(' '.join(completion_list))


class CommandsLabel(QLabel):
    def __init__(self, parent, tconfig):
        super().__init__(parent)
        self.tconfig = tconfig
        self.init_ui()

    def init_ui(self):
        screen = QDesktopWidget().availableGeometry()
        self.move(310, 0)
        self.resize(screen.width() - self.width(), self.tconfig.height)


if __name__ == '__main__':
    app = QApplication(sys.argv)

    tconfig = ThrawnConfig()

    panel = Panel(tconfig)
    panel.show()

    sys.exit(app.exec_())
