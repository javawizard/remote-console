
import code
import socket
import threading
import inspect
import sys
import pydoc

# The entire first half of this module is dedicated to swapping out sys.stdout,
# sys.stderr, and sys.stdin with file-like objects that act as proxies for the
# remote console connection tied to the current thread, all in order to get
# print statements and such things to send their output to the correct console.
# There has /got/ to be a better way to do this...
# 
# Having a custom stdout confuses pydoc (and hence the built-in help function)
# into never using the platform's native pager, so we'll patch it up to still
# use it when invoked from the main console.

_former_thread_class = threading.Thread
_former_stdout = sys.stdout
_former_stderr = sys.stderr
_former_stdin = sys.stdin

class _StreamTracker(threading.local):
    stdout = _former_stdout
    stderr = _former_stderr
    stdin = _former_stdin
    # Note that this is being called before we've swapped out stdout. Also note
    # that we wrap it with staticmethod to prevent it from being wrapped in a
    # bound method by _StreamTracker. TODO: Figure out a less kludgy way to do
    # this.
    pager = staticmethod(pydoc.getpager())

_stream_tracker = _StreamTracker()


def _pager(text):
    _stream_tracker.pager(text)

pydoc.pager = _pager


def _make_wrapper(name):
    def function(*args, **kwargs):
        self, args = args[0], args[1:]
        # self is our local _StreamWrapper instance; don't pass it into the
        # underlying socket file-like object
        return getattr(getattr(_stream_tracker, self._stream_type), name)(*args)
    return function

class _StreamWrapper(object):
    def __init__(self, stream_type):
        self._stream_type = stream_type
    
    # Unilaterally block attempts to close ourselves for now to prevent an
    # attempt to close stdout from inadvertently closing stdin and stderr as
    # they're all set to the file wrapper around the connection's socket. This
    # might cause problems arising from our real stdout/err/in not ever being
    # closed properly, so some changes might be needed here.
    def close(self):
        pass
    
    flush = _make_wrapper("flush")
    fileno = _make_wrapper("fileno")
    isatty = _make_wrapper("isatty")
    next = _make_wrapper("next")
    read = _make_wrapper("read")
    readline = _make_wrapper("readline")
    readlines = _make_wrapper("readlines")
    xreadlines = _make_wrapper("xreadlines")
    seek = _make_wrapper("seek")
    tell = _make_wrapper("tell")
    truncate = _make_wrapper("truncate")
    write = _make_wrapper("write")
    writelines = _make_wrapper("writelines")

sys.stdout = _StreamWrapper("stdout")
sys.stderr = _StreamWrapper("stderr")
sys.stdin = _StreamWrapper("stdin")

# ...and now that we're finally done with stream swapping, we can get onto the
# fun stuff, the actual remote console bit.

BANNER = ('Python %s on %s\nType "help", "copyright", "credits" or "license" '
          'for more information.' % (sys.version, sys.platform))

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
            print >>_former_stdout, "Remote console session disconnected: %s" % e
            self.connection.close()
            self.connection = None
            raise EOFError()
    
    def run(self):
        _stream_tracker.stdout = self.connection
        _stream_tracker.stderr = self.connection
        _stream_tracker.stdin = self.connection
        # Note that this is being called after we've swapped out stdout, so
        # it'll give us back a plain pager
        _stream_tracker.pager = pydoc.getpager()
        try:
            self.interact(BANNER)
        except SystemExit:
            print >>_former_stdout, "Remote console session disconnecting on a call to exit()"
            self.connection.close()
            self.connection = None


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












