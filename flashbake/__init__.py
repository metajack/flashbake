import os
import logging
import sys
from types import *

class ControlConfig:
    """
    Gather control options parsed out of the dot-control file in a project.
    """

    def __init__(self):
        self.feed = None
        self.limit = 3
        self.author = None

        self.email = None
        self.notice_to = None
        self.notice_from = None
        self.smtp_port = 25

        self.int_props = list()
        self.int_props.append('smtp_port')
        self.int_props.append('limit')
        self.plugins = list()

    def capture(self, line):
        # grab comments but don't do anything
        if line.startswith('#'):
            return True

        # grab blanks but don't do anything
        if len(line.strip()) == 0:
            return True

        if line.find(':') > 0:
            prop_tokens = line.split(':', 1)
            prop_name = prop_tokens[0].strip()
            prop_value = prop_tokens[1].strip()

            if 'plugins' == prop_name:
               self.initplugins(prop_value.split(','))
               return True

            # only capture explicitly initialized attributes
            if not prop_name in self.__dict__:
                logging.debug('Ignoring unkown property, %s' % prop_name)
                return True

            if prop_name in self.int_props:
                prop_value = int(prop_value)
            self.__dict__[prop_name] = prop_value

            return True

        return False

    def fix(self):
        """
        Do any property clean up, after parsing but before use
        """

        if self.notice_from == None and self.notice_to != None:
            self.notice_from = self.notice_to

        if len(self.plugins) == 0:
            logging.debug('No plugins configured, enabling the stock set.')
            self.initplugins(('flashbake.plugins.timezone',
                    'flashbake.plugins.weather',
                    'flashbake.plugins.uptime',
                    'flashbake.plugins.feed'))

        if self.feed == None or self.author == None or self.notice_to == None:
            logging.error('Make sure that feed:, author:, and notice_to: are in the .control file')
            sys.exit(1)

    def initplugins(self, plugin_names):
        for plugin_name in plugin_names:
            plugin = initplugin(plugin_name)
            self.plugins.append(plugin)

    def initplugin(self, plugin_name):
        try:
            __import__(plugin_name)
        except ImportError:
            logging.warn('Invalid module, %s' % plugin_name)
            return None

        plugin_module = sys.modules[plugin_name]

        if 'connectable' not in plugin_module.__dict__:
            logging.warn('Plugin, %s, must have a connectable property.' % plugin_name)
            return None

        if not isinstance(plugin_module.connectable, bool):
            logging.warn('Connectable property of plugin, %s, must be boolean.' % plugin_name)
            return None

        if plugin_module.addcontext == None:
            logging.warn('Plugin, %s, doesn\'t provide the addcontext function.' % plugin_name)
            return None

        return plugin_module

class ParseResults:
    """
    Track the files as they are parsed and manipulated with regards to their git
    status and the dot-control file.
    """
    def __init__(self):
        self.linked_files = dict()
        self.control_files = set()
        self.not_exists = set()
        self.to_add = set()

    def addfile(self, filename):
        link = self.checklink(filename)

        if link == None:
            self.control_files.add(filename)
        else:
            self.linked_files[filename] = link

    def checklink(self, filename):
        if os.path.islink(filename):
           return filename
        directory = os.path.dirname(filename)

        while (len(directory) > 0):
            if os.path.islink(directory):
                return directory
            directory = os.path.dirname(directory)
        return None

    def contains(self, filename):
        return filename in self.control_files

    def remove(self, filename):
        self.control_files.remove(filename)

    def putabsent(self, filename):
        self.not_exists.add(filename)

    def putneedsadd(self, filename):
        self.to_add.add(filename)

    def warnlinks(self):
        # print warnings for linked files
        for (filename, link) in self.linked_files.iteritems():
            logging.info('%s is a link or its directory path contains a link.' % filename)

    def addorphans(self, control_config):
        if len(self.to_add) == 0:
            return

        message_file = context.buildmessagefile(control_config)

        add_template = 'git add "%s"'
        git_commit = 'git commit -F %(msg_filename)s %(filenames)s'
        file_template = ' "%s"'
        to_commit = ''
        for orphan in self.to_add:
            logging.debug('Adding %s.' % orphan)
            add_output = commands.getoutput(add_template % orphan)
            to_commit += file_template % orphan

        logging.info('Adding new files, %s.' % to_commit)
        # consolidate the commit to be friendly to how git normally works
        git_commit = git_commit % {'msg_filename' : message_file, 'filenames' : to_commit}
        logging.debug(git_commit)
        commit_output = commands.getoutput(git_commit)

        os.remove(message_file)

    def needsnotice(self):
        return len(self.not_exists) > 0 or len(self.linked_files) > 0
