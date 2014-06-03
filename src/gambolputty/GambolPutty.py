#!/usr/bin/python
# -*- coding: UTF-8 -*-
import pprint
import Utils
import multiprocessing
import StatisticCollector as StatisticCollector
import sys
import os
import signal
import time
import getopt
import logging.config
import threading
import Queue
import yaml

module_dirs = ['input',
               'parser',
               'modifier',
               'misc',
               'output',
               'webserver',
               'cluster']

# Expand the include path to our libs and modules.
# TODO: Check for problems with similar named modules in
# different module directories.
pathname = os.path.abspath(__file__)
pathname = pathname[:pathname.rfind("/")]
[sys.path.append(pathname + "/" + mod_dir) for mod_dir in module_dirs]

class Node:
    def __init__(self, module):
        self.children = []
        self.module = module

    def addChild(self, node):
        self.children.append(node)

def hasLoop(node, stack=[]):
    if not stack:
        stack.append(node)
    for current_node in node.children:
        if current_node in stack:
            return [current_node]
        stack.append(current_node)
        return hasLoop(current_node, stack)
    return []

class GambolPutty():
    """A stream parser with configurable modules and message paths.

    GambolPutty helps to parse text based streams by providing a framework of modules.
    These modules can be combined via a simple configuration in any way you like. Have
    a look at the example config gambolputty.conf.example in the conf folder.

    This is the main class that reads the configuration, includes the needed modules
    and connects them via queues as configured.
    """

    def __init__(self, path_to_config_file=False):
        self.alive = False
        self.main_process_pid = os.getpid()
        self.is_master = True
        self.modules = {}
        self.logger = logging.getLogger(self.__class__.__name__)
        if path_to_config_file:
            self.readConfiguration(path_to_config_file)

    def produceQueue(self, module_instance, queue_max_size=20, queue_buffer_size=100):
        """Returns a queue with queue_max_size"""
        if isinstance(module_instance, threading.Thread):
            return Queue.Queue(queue_max_size)
        if isinstance(module_instance, multiprocessing.Process):
            if Utils.zmq_avaiable:
                queue = Utils.BufferedQueue(Utils.ZeroMqMpQueue(queue_max_size), queue_buffer_size)
            else:
                queue = Utils.BufferedQueue(multiprocessing.Queue(queue_max_size), queue_buffer_size)
            return queue

    def readConfiguration(self, path_to_config_file):
        """Loads and parses the configuration

        :param path_to_config_file: path to the configuration file
        :type path_to_config_file: str
        """
        try:
            conf_file = open(path_to_config_file)
            self.configuration = yaml.load(conf_file)
        except:
            etype, evalue, etb = sys.exc_info()
            self.logger.error("%sCould not read config file %s. Exception: %s, Error: %s.%s" % (
            Utils.AnsiColors.WARNING, path_to_config_file, etype, evalue, Utils.AnsiColors.ENDC))
            self.shutDown()

    def getConfiguration(self):
        return self.configuration

    def setConfiguration(self, configuration, merge=True):
        if type(configuration) is not list:
            return
        if merge:
            # If merge is true keep currently configured modules and only merge new ones.
            for module_info in configuration:
                if module_info not in self.configuration:
                    self.configuration.append(module_info)
        else:
            self.configuration = configuration

    def configure(self):
        gp_conf = {}
        for idx, configuration in enumerate(self.configuration):
            if 'GambolPutty' in configuration:
                gp_conf = self.configuration.pop(idx)
                break
        self.default_pool_size = configuration['default_pool_size'] if 'default_pool_size' in gp_conf else multiprocessing.cpu_count() - 1

    def initModule(self, module_name):
        """ Initalize a module.

        :param module_name: module to initialize
        :type module_name: string
        """
        self.logger.debug("Initializing module %s." % (module_name))
        try:
            module = __import__(module_name)
            module_class = getattr(module, module_name)
            instance = module_class(self, StatisticCollector.StatisticCollector())
        except:
            etype, evalue, etb = sys.exc_info()
            self.logger.warning("%sCould not init module %s. Exception: %s, Error: %s.%s" % (Utils.AnsiColors.WARNING, module_name, etype, evalue, Utils.AnsiColors.ENDC))
            self.shutDown()
        return instance

    def initModulesFromConfig(self):
        """ Initalize all modules from the current config.

            The pool size defines how many threads for this module will be started.
        """
        # Init modules as defined in config
        for idx, module_info in enumerate(self.configuration):
            module_config = {}
            module_id = None
            if isinstance(module_info, dict):
                module_class_name = module_info.keys()[0]
                module_config = module_info[module_class_name]
                # Set module name. Use id if it was set in configuration.
                try:
                    module_id = module_class_name if 'id' not in module_config else module_config['id']
                except:
                    etype, evalue, etb = sys.exc_info()
                    self.logger.error("%sError in configuration file for module %s. Exception: %s, Error: %s. Please check configuration.%s" % (Utils.AnsiColors.FAIL, module_class_name, etype, evalue, Utils.AnsiColors.ENDC))
                    self.shutDown()
            else:
                module_id = module_class_name = module_info
            counter = 1
            while module_id in self.modules:
                tmp_mod_name = module_id.split("_",1)[0]
                module_id = "%s_%s" % (tmp_mod_name, counter)
                counter += 1
            # Set some app wide defaults.
            pool_size = module_config['pool_size'] if "pool_size" in module_config else self.default_pool_size
            module_instances = []
            for _ in range(pool_size):
                # Build first instance.
                module_instance = self.initModule(module_class_name)
                # Append to internal list.
                module_instances.append(module_instance)
                # If instance is not configured to run in parallel, only create one instance, no matter what the pool_size configuration says.
                if not module_instance.can_run_parallel:
                    break
            self.modules[module_id] = {  'idx': idx,
                                         'instances': module_instances,
                                         'type': module_instance.module_type,
                                         'configuration': module_config}

            # Set receiver to next module in config if no receivers were set.
            if 'receivers' not in module_config:
                try:
                    next_module_info = self.configuration[idx+1]
                    if isinstance(next_module_info, dict):
                        receiver_class_name = next_module_info.keys()[0]
                        receiver_id = receiver_class_name if (not next_module_info[receiver_class_name] or 'id' not in next_module_info[receiver_class_name]) else next_module_info[receiver_class_name]['id']
                    else:
                        receiver_id = receiver_class_name = next_module_info
                    counter = 1
                    while receiver_id in self.modules:
                        tmp_mod_name = receiver_id.split("_",1)[0]
                        receiver_id = "%s_%s" % (tmp_mod_name, counter)
                        counter += 1
                    module_config['receivers'] = [receiver_id]
                except IndexError:
                    module_config['receivers'] = [None]
                except:
                    # Something is wrong with the configuration. Tell user.
                    etype, evalue, etb = sys.exc_info()
                    self.logger.error("%sError in configuration for module %s. Exception: %s, Error: %s. Please check configuration.%s" % ( Utils.AnsiColors.FAIL, module_config, etype, evalue, Utils.AnsiColors.ENDC))
                    self.shutDown()

    def configureModules(self):
        # Call configuration of module
        for module_name, module_info in sorted(self.modules.items(), key=lambda x: x[1]['idx']):
            for module_instance in module_info['instances']:
                module_instance.configure(module_info['configuration'])

    def initEventStream(self):
        """ Connect modules.

        The configuration allows to connect the modules via the <receivers> parameter.
        This method creates the queues and connects the modules via this queues.
        To prevent loops a sanity check is performed before all modules are connected.
        """
        # All modules are initialized, connect producer and consumers via a queue.
        queues = {}
        module_loop_buffer = []
        for module_name, module_info in self.modules.iteritems():
            # Iterate over all instances
            instance = module_info['instances'][0]
            for receiver_data in instance.getConfigurationValue('receivers'):
                if not receiver_data:
                    break
                if isinstance(receiver_data, dict):
                    receiver_name, _ = receiver_data.iteritems().next()
                else:
                    receiver_name = receiver_data
                self.logger.debug("%s will send its output to %s." % (module_name, receiver_name))
                if receiver_name not in self.modules:
                    self.logger.warning( "%sCould not add %s as receiver for %s. Module not found.%s" % ( Utils.AnsiColors.WARNING, receiver_name, module_name, Utils.AnsiColors.ENDC))
                    continue
                for receiver_instance in self.modules[receiver_name]['instances']:
                    # If the receiver is a thread or a process, produce the needed queue.
                    if isinstance(receiver_instance, threading.Thread) or isinstance(receiver_instance, multiprocessing.Process):
                        if receiver_name not in queues:
                            if isinstance(receiver_instance, threading.Thread):
                                queues[receiver_name] = self.produceQueue(receiver_instance, receiver_instance.getConfigurationValue('queue_size'))
                            else:
                                queues[receiver_name] = self.produceQueue(receiver_instance, receiver_instance.getConfigurationValue('queue_size'), receiver_instance.getConfigurationValue('queue_buffer_size'))
                        try:
                            if not receiver_instance.getInputQueue():
                                receiver_instance.setInputQueue(queues[receiver_name])
                        except AttributeError:
                            self.logger.error("%s%s can not be set as receiver. It seems to be incompatible." % (Utils.AnsiColors.WARNING, receiver_name, Utils.AnsiColors.ENDC))
                    # Build a node structure used for the loop test.
                    try:
                        node = (node for node in module_loop_buffer if node.module == instance).next()
                    except:
                        node = Node(instance)
                        module_loop_buffer.append(node)
                    try:
                        receiver_node = (node for node in module_loop_buffer if node.module == receiver_instance).next()
                    except:
                        receiver_node = Node(receiver_instance)
                        module_loop_buffer.append(receiver_node)
                    node.addChild(receiver_node)
                for instance in module_info['instances']:
                    # Add the receiver to senders. If the receiver is a thread or multiprocess, they share the same queue.
                    if isinstance(receiver_instance, threading.Thread) or isinstance(receiver_instance, multiprocessing.Process):
                        instance.addReceiver(receiver_name, queues[receiver_name])
                    else:
                        instance.addReceiver(receiver_name, receiver_instance)
        # Check if the configuration produces a loop.
        # This code can definitely be made more efficient...
        for node in module_loop_buffer:
            for loop in hasLoop(node, stack=[]):
                self.logger.error(
                    "%sChaining of modules produced a loop. Check configuration. Module: %s.%s" % ( Utils.AnsiColors.FAIL, loop.module.__class__.__name__, Utils.AnsiColors.ENDC))
                self.shutDown()

    def getModuleInfoById(self, module_id, silent=True):
        try:
            return self.modules[module_id]
        except KeyError:
            if not silent:
                self.logger.error("%sGet module by id %s failed. No such module.%s" % (Utils.AnsiColors.FAIL, module_id, Utils.AnsiColors.ENDC))
            return None

    def runModules(self):
        """
        Start the configured modules
        """
        # All modules are completely configured, call modules run method if it exists.
        for module_name, module_info in sorted(self.modules.items(), key=lambda x: x[1]['idx']):
            if len(module_info['instances']) > 1 and module_info['instances'][0].can_run_parallel:
                start_message = "%sUsing module %s, pool size: %s%s." % (Utils.AnsiColors.LIGHTBLUE, module_name, len(module_info['instances']), Utils.AnsiColors.ENDC)
            else:
                start_message = "%sUsing module %s%s." % (Utils.AnsiColors.LIGHTBLUE, module_name, Utils.AnsiColors.ENDC)
            if self.is_master:
                self.logger.info(start_message)
            for instance in module_info['instances']:
                name = module_info['id'] if 'id' in module_info else module_name
                try:
                    if isinstance(instance, threading.Thread) or isinstance(instance, multiprocessing.Process):
                        # The default 'start' method of threading.Thread will call the 'run' method of the module.
                        instance.start()
                    elif getattr(instance, "run", None):
                        instance.run()
                except:
                    etype, evalue, etb = sys.exc_info()
                    self.logger.warning("%sError calling run/start method of %s. Exception: %s, Error: %s.%s" % (Utils.AnsiColors.WARNING, name, etype, evalue, Utils.AnsiColors.ENDC))
                if not instance.can_run_parallel:
                    break

    def runChildren(self, family_count=0):
        self.children = []
        print "runChildren method called in %s" % os.getpid()
        if family_count == 0 or family_count > multiprocessing.cpu_count():
            family_count = multiprocessing.cpu_count() - 1
        for i in range(family_count):
            pid = os.fork()
            if pid == 0:
                #print "Childprocess %s" % os.getpid()
                self.is_master = False
                self.run()
                break
            #print "forked pid %s" % pid
            self.children.append(pid)
        self.run()

    def run(self):
        self.alive = True
        print "Run method called in %s" % os.getpid()
        # Catch Keyboard interrupt here. Catching the signal seems
        # to be more reliable then using try/except when running
        # multiple processes under pypy.
        signal.signal(signal.SIGINT, self.shutDown)
        signal.signal(signal.SIGALRM, self.restart)
        self.runModules()
        if self.is_master:
            self.logger.info("%sGambolPutty started with %s processes.%s" % (Utils.AnsiColors.LIGHTBLUE, len(self.children)+1, Utils.AnsiColors.ENDC))
        import tornado.ioloop
        tornado.ioloop.IOLoop.instance().start()
        #while self.alive:
        #    time.sleep(.5)

    def restart(self, signum=False, frame=False):
        # If a module started a subprocess, the whole gambolputty parent process gets forked.
        # As a result, the forked gambolputty process will also catch SIGINT||SIGALARM.
        # Still we know the pid of the original main process.
        is_forked_process = self.main_process_pid != os.getpid()
        if self.is_master:
            self.logger.info("%sRestarting GambolPutty.%s" % (Utils.AnsiColors.LIGHTBLUE, Utils.AnsiColors.ENDC))
        self.shutDownModules()
        self.configure()
        self.initModulesFromConfig()
        self.configureModules()
        self.initEventStream()
        self.runModules()

    def shutDown(self, signum=False, frame=False):
        # If a module started a subprocess, the whole gambolputty parent process gets forked.
        # As a result, the forked gambolputty process will also catch SIGINT||SIGALARM.
        # Still we know the pid of the original main process and ignore SIGINT||SIGALARM in forked processes.
        # Directly exit on a second SIGINT||SIGALARM.
        if not self.alive:
            sys.exit(0)
        self.alive = False
        if self.is_master:
            self.logger.info("%sShutting down GambolPutty.%s" % (Utils.AnsiColors.LIGHTBLUE, Utils.AnsiColors.ENDC))
        self.shutDownModules()
        Utils.TimedFunctionManager.stopTimedFunctions()
        if self.is_master:
            self.logger.info("%sShutdown complete.%s" % (Utils.AnsiColors.LIGHTBLUE, Utils.AnsiColors.ENDC))
        sys.exit(0)

    def shutDownModules(self):
        import tornado.ioloop
        tornado.ioloop.IOLoop.instance().stop()
        # Shutdown all input modules.
        for module_name, module_info in self.modules.iteritems():
            silent=False
            for instance in module_info['instances']:
                if instance.module_type == "input":
                    instance.shutDown(silent)
                    silent=True
        # Get all configured queues to check for pending events.
        module_queues = {}
        for module_name, module_info in self.modules.iteritems():
            instance = module_info['instances'][0]
            if not hasattr(instance, 'getInputQueue') or not instance.getInputQueue():
                continue
            module_queues[module_name] = instance.getInputQueue()
        if len(module_queues) > 0:
            wait_loops = 0
            while wait_loops < 5:
                wait_loops += 1
                events_in_queues = 0
                for module_name, queue in module_queues.iteritems():
                    events_in_queues += queue.qsize()
                if events_in_queues > 0:
                    # Give remaining queued events some time to finish.
                    if self.is_master == os.getpid():
                        self.logger.info("%s%s event(s) still in flight. Waiting %s secs. Press ctrl+c again to exit directly.%s" % (Utils.AnsiColors.LIGHTBLUE, events_in_queues, (.5 * wait_loops),Utils.AnsiColors.ENDC))
                    time.sleep(.5 * wait_loops)
                    continue
                break
        # Shutdown all other modules.
        for module_name, module_info in self.modules.iteritems():
            silent = not self.is_master
            for instance in module_info['instances']:
                if instance.module_type != "input":
                    instance.shutDown(silent)
                    silent=True

def usage():
    print 'Usage: ' + sys.argv[0] + ' -c <path/to/config.conf> --configtest'

if "__main__" == __name__:
    config_pathname = os.path.abspath(sys.argv[0])
    config_pathname = config_pathname[:config_pathname.rfind("/")] + "/../conf"
    logging.config.fileConfig('%s/logger.conf' % config_pathname)
    logger = logging.getLogger("GambolPutty")
    path_to_config_file = ""
    run_configtest = False
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hc:", ["help", "configtest","conf="])
    except getopt.GetoptError:
        usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-c", "--conf"):
            path_to_config_file = arg
        elif opt in ("--configtest"):
            run_configtest = True
    if not path_to_config_file:
        logger.error("%sPlease provide a path to a configuration.%s" % (Utils.AnsiColors.FAIL, Utils.AnsiColors.ENDC))
        usage()
        sys.exit(2)
    if not os.path.isfile(path_to_config_file):
        logger.error("%sConfigfile %s could not be found.%s" % (Utils.AnsiColors.FAIL, path_to_config_file, Utils.AnsiColors.ENDC))
        usage()
        sys.exit(2)
    gp = GambolPutty(path_to_config_file)
    gp.configure()
    gp.initModulesFromConfig()
    gp.configureModules()
    gp.initEventStream()
    if run_configtest:
        logger.info("%sConfigurationtest for %s finished.%s" % (Utils.AnsiColors.LIGHTBLUE, path_to_config_file, Utils.AnsiColors.ENDC))
        sys.exit(0)
    gp.runChildren()