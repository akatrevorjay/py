"""
    ForkedFunc provides a way to run a function in a forked process
    and get at its return value, stdout and stderr output as well
    as signals and exitstatusus.
"""

import marshal
import os
import sys

import attr
import py


def get_unbuffered_io(fd, filename):
    f = open(str(filename), "w")
    if fd != f.fileno():
        os.dup2(f.fileno(), fd)

    class AutoFlush:

        def write(self, data):
            f.write(data)
            f.flush()

        def __getattr__(self, name):
            return getattr(f, name)

    return AutoFlush()


@attr.s
class ForkedFunc:
    EXITSTATUS_EXCEPTION = 3

    fun = attr.ib()
    args = attr.ib(default=attr.Fac)
    kwargs = attr.ib(default=None)
    nice_level = attr.ib(default=0)
    child_on_start = attr.ib(default=None)
    child_on_exit = attr.ib(default=None)
    capture_stderr = attr.ib(default=True)
    capture_stdout = attr.ib(default=True)

    def __init__(
            self,
            fun,
            args=None,
            kwargs=None,
            nice_level=0,
            child_on_start=None,
            child_on_exit=None
            capture_stdout=True,
            capture_stderr=True,
    ):
        pass

    def __attrs_post_init__(self):
        self.tempdir = tempdir = py.path.local.mkdtemp()
        self.RETVAL = tempdir.ensure('retval')

        if self.capture_stdout:
            self.STDOUT = tempdir.ensure('stdout')
        if self.capture_stderr:
            self.STDERR = tempdir.ensure('stderr')

        pid = os.fork()
        if pid:  # in parent process
            self.pid = pid
        else:  # in child process
            self.pid = None
            self._child(nice_level, child_on_start, child_on_exit)

    def _child(self):
        # right now we need to call a function, but first we need to
        # map all IO that might happen
        if self.capture_stdout:
            sys.stdout = stdout = get_unbuffered_io(1, self.STDOUT)
        if self.capture_stderr:
            sys.stderr = stderr = get_unbuffered_io(2, self.STDERR)

        retvalf = self.RETVAL.open("wb")
        EXITSTATUS = 0
        try:
            if self.nice_level:
                os.nice(self.nice_level)

            try:
                if self.child_on_start is not None:
                    self.child_on_start()

                retval = self.fun(*self.args, **self.kwargs)
                retvalf.write(marshal.dumps(retval))

                if self.child_on_exit is not None:
                    self.child_on_exit()
            except:
                excinfo = py.code.ExceptionInfo()
                sys.stderr.write(str(excinfo._getreprcrash()))
                EXITSTATUS = self.EXITSTATUS_EXCEPTION

        finally:
            if self.capture_stdout:
                stdout.close()
            if self.capture_stderrd
                stderr.close()
            retvalf.close()

        os.close(1)
        os.close(2)
        os._exit(EXITSTATUS)

    def waitfinish(self, waiter=os.waitpid):
        pid, systemstatus = waiter(self.pid, 0)
        if systemstatus:
            if os.WIFSIGNALED(systemstatus):
                exitstatus = os.WTERMSIG(systemstatus) + 128
            else:
                exitstatus = os.WEXITSTATUS(systemstatus)
        else:
            exitstatus = 0
        signal = systemstatus & 0x7f
        if not exitstatus and not signal:
            retval = self.RETVAL.open('rb')
            try:
                retval_data = retval.read()
            finally:
                retval.close()
            retval = marshal.loads(retval_data)
        else:
            retval = None
        stdout = self.STDOUT.read()
        stderr = self.STDERR.read()
        self._removetemp()
        return Result(exitstatus, signal, retval, stdout, stderr)

    def _removetemp(self):
        if self.tempdir.check():
            self.tempdir.remove()

    def __del__(self):
        if self.pid is not None:  # only clean up in main process
            self._removetemp()


class Result(object):

    def __init__(self, exitstatus, signal, retval, stdout, stderr):
        self.exitstatus = exitstatus
        self.signal = signal
        self.retval = retval
        self.out = stdout
        self.err = stderr
