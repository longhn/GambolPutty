# -*- coding: utf-8 -*-
import tornado.web
import BaseModule
import Decorators
import Utils
import handler.ActionHandler
import handler.HtmlHandler
import handler.WebsocketHandler
#import uimodules.ServerListItem

@Decorators.ModuleDocstringParser
class WebGui(BaseModule.BaseModule):
    """
    A WebGui plugin for GambolPutty. At the moment this is just a stub.

    Module dependencies:    WebserverTornado

    Configuration template:

    tornado_webserver: Name of the webserver module.
    document_root: Path to look for templates and static files.

    - WebGui:
        tornado_webserver: webserver          # <default: 'WebserverTornado'; type: string; is: optional>
        document_root: other_root             # <default: 'docroot'; type: string; is: optional>
    """
    module_type = "stand_alone"
    """Set module type"""

    can_run_forked = False

    def configure(self, configuration):
        # Call parent configure method
        BaseModule.BaseModule.configure(self, configuration)
        # Get tornado webserver module instance.
        mod_info = self.gp.getModuleInfoById(self.getConfigurationValue('tornado_webserver'))
        if not mod_info:
            self.logger.error("Could not start web gui module. Required webserver module %s not found. Please check your configuration." % (self.getConfigurationValue('tornado_webserver')))
            self.gp.shutDown()
            return
        self.webserver_module = mod_info['instances'][0]
        self.webserver_module.addHandlers(self.getHandlers())

    def getHandlers(self):
        settings = self.webserver_module.getSettings()
        handlers =  [# HtmlHandler
                     (r"/", handler.HtmlHandler.MainHandler),
                     # StaticFilesHandler
                     (r"/images/(.*)",tornado.web.StaticFileHandler, {"path": "%s/images/" % settings['static_path']}),
                     (r"/css/(.*)",tornado.web.StaticFileHandler, {"path": "%s/css/" % settings['static_path']}),
                     (r"/js/(.*)",tornado.web.StaticFileHandler, {"path": "%s/js/" % settings['static_path']},),
                     # ActionHandler
                     (r"/actions/restart", handler.ActionHandler.RestartHandler),
                     (r"/actions/get_server_info", handler.ActionHandler.GetServerInformation),
                     # WebsocketHandler
                     (r"/websockets/statistics", handler.WebsocketHandler.StatisticsWebSocketHandler),
                     (r"/websockets/get_logs", handler.WebsocketHandler.LogToWebSocketHandler)]
        return handlers