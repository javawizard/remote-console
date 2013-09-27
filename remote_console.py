
import code
import socket
import threading
import inspect
import sys

_former_thread_class = threading.Thread
_former_stdout = sys.stdout
_former_stderr = sys.stderr
_former_stdin = sys.stdin


class RemoteConsole(_former_thread_class, code.InteractiveConsole):
    def __init__(self, connection, local_vars):
        _former_thread_class.__init__(self)
        code.InteractiveConsole.__init__(self, local_vars)
        self.connection = connection
    
    def write(self, text):
        if self.connection:
            self.connection.write(text)
            self.connection.flush()
    
    def raw_input(self, prompt=""):
        self.write(prompt)
        try:
            text = self.connection.readline()
            if not text:
                raise Exception("Remote end closed the connection")
            return text
        except BaseException as e:
            print "Telnet console session disconnected: %s" % e
            self.connection.close()
            self.connection = None
            raise EOFError()
    
    def run(self):
        self.interact()


class RemoteConsoleServer(_former_thread_class):
    def __init__(self, port, host="127.0.0.1", local_vars=None):
        _former_thread_class.__init__(self)
        if local_vars is None:
            # Use the locals from the topmost frame. This is the closest I've
            # come to implicitly using the main console's locals if a dict
            # isn't explicitly specified.
            frame = inspect.currentframe()
            while frame.f_back:
                frame = frame.f_back
            local_vars = frame.f_locals
        self.host = host
        self.port = port
        self.local_vars = local_vars
        self.setDaemon(True)
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(10)
    
    def run(self):
        # TODO: We're basically reimplementing most of socketserver.TCPServer
        # with socketserver.ThreadingMixIn mixed in; we might as well just
        # reuse those classes.
        while True:
            s, _ = self.server.accept()
            connection = s.makefile()
            s.close()
            self.start_remote_console(connection)
    
    def start_remote_console(self, connection):
        RemoteConsole(connection, self.local_vars).start()
    
    def close(self):
        self.server.close()


def listen(port):
    RemoteConsoleServer(port).start()












