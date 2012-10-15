# -*- encoding: utf-8 -*-
#
# :authors: Arturo Filastò
# :licence: see LICENSE

from twisted.python import log
from twisted.application import service, internet, app
from twisted.python.runtime import platformType

from globaleaks.db import createTables

class GLBaseRunner(app.ApplicationRunner):
    """
    This is a specialized runner that is responsible for starting the specified
    service.
    The purpose of it is to do the equivalent of what would be done with
    launching twistd from command line (daemonizing the process, creating the
    PID file, etc).
    """
    def preApplication(self):
        """
        We don't actually want to override this method since there is nothing
        interesting to do in here.
        """
        pass

    def postApplication(self):
        """
        We must place all the operations to be done before the starting of the
        application.
        Here we will take care of the launching of the reactor and the
        operations to be done after it's shutdown.
        """
        pass

if platformType == "win32":
    from twisted.scripts._twistw import ServerOptions, \
        WindowsApplicationRunner
    class GLBaseRunnerWindows(WindowsApplicationRunner):
        """
        This runner is specific to windows.
        """
        def postApplication(self):
            """
            This code is taken directly from the method postApplication of
            WindowsApplicationRunner.
            """
            def runApp(res):
                """
                Start the actual service Application.
                """
                service.IService(self.application).privilegedStartService()
                app.startApplication(self.application, not self.config['no_save'])
                app.startApplication(internet.TimerService(0.1, lambda:None), 0)

            print "WARNING! Windows is not tested!"
            d = createTables()
            d.addCallback(runApp)

            self.startReactor(None, self.oldstdout, self.oldstderr)
            log.msg("Server Shut Down.")

    GLBaseRunner = GLBaseRunnerWindows
else:
    from twisted.scripts._twistd_unix import ServerOptions, \
        UnixApplicationRunner
    ServerOptions = ServerOptions
    class GLBaseRunnerUnix(UnixApplicationRunner):
        """
        This runner is specific to Unix systems.
        """
        def postApplication(self):
            """
            THis code is taken directly from UnixApplicationRunner
            """
            def runApp(res):
                """
                Start the actual service Application.
                """
                self.startApplication(self.application)
                print "GLBackend is now running"
                print "Visit http://127.0.0.1:8082/index.html to interact with me"

            d = createTables()
            d.addBoth(runApp)

            self.startReactor(None, self.oldstdout, self.oldstderr)
            self.removePID(self.config['pidfile'])

    GLBaseRunner = GLBaseRunnerUnix