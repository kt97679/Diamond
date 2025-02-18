# coding=utf-8

"""
Collect HAProxy Stats

#### Dependencies

 * urlparse
 * urllib2

"""

import re
from urllib.request import Request, urlopen
import base64
import csv
import socket
import diamond.collector


class HAProxyCollector(diamond.collector.Collector):

    def get_default_config_help(self):
        config_help = super(HAProxyCollector, self).get_default_config_help()
        config_help.update({
            'method': "Method to use for data collection. Possible values: " +
                      "http, unix",
            'url': "Url to stats in csv format",
            'user': "Username",
            'pass': "Password",
            'sock': "Path to admin UNIX-domain socket",
            'ignore_servers': "Ignore servers, just collect frontend and " +
                              "backend stats",
        })
        return config_help

    def get_default_config(self):
        """
        Returns the default collector settings
        """
        config = super(HAProxyCollector, self).get_default_config()
        config.update({
            'method':           'http',
            'path':             'haproxy',
            'url':              'http://localhost/haproxy?stats;csv',
            'user':             'admin',
            'pass':             'password',
            'sock':             '/var/run/haproxy.sock',
            'ignore_servers':   False,
        })
        return config

    def _get_config_value(self, section, key):
        if section:
            if section not in self.config:
                self.log.error("Error: Config section '%s' not found", section)
                return None
            return self.config[section].get(key, self.config[key])
        else:
            return self.config[key]

    def http_get_csv_data(self, section=None):
        """
        Request stats from HAProxy Server
        """
        metrics = []
        req = Request(self._get_config_value(section, 'url'))
        try:
            handle = urlopen(req)
            return handle.readlines()
        except Exception as e:
            if not hasattr(e, 'code') or e.code != 401:
                self.log.error("Error retrieving HAProxy stats. %s", e)
                return metrics

        # get the www-authenticate line from the headers
        # which has the authentication scheme and realm in it
        authline = e.headers['www-authenticate']

        # this regular expression is used to extract scheme and realm
        authre = (r'''(?:\s*www-authenticate\s*:)?\s*''' +
                  '''(\w*)\s+realm=['"]([^'"]+)['"]''')
        authobj = re.compile(authre, re.IGNORECASE)
        matchobj = authobj.match(authline)
        if not matchobj:
            # if the authline isn't matched by the regular expression
            # then something is wrong
            self.log.error('The authentication header is malformed.')
            return metrics

        scheme = matchobj.group(1)
        # here we've extracted the scheme
        # and the realm from the header
        if scheme.lower() != 'basic':
            self.log.error('Invalid authentication scheme.')
            return metrics

        base64string = base64.encodestring(
            '%s:%s' % (self._get_config_value(section, 'user'),
                       self._get_config_value(section, 'pass')))[:-1]
        authheader = 'Basic %s' % base64string
        req.add_header("Authorization", authheader)
        try:
            handle = urlopen(req)
            metrics = handle.readlines()
            return metrics
        except IOError as e:
            # here we shouldn't fail if the USER/PASS is right
            self.log.error("Error retrieving HAProxy stats. " +
                           "(Invalid username or password?) %s", e)
            return metrics

    def unix_get_csv_data(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        data = str()

        try:
            sock.connect(self.config['sock'])
            sock.send('show stat\n')
            while 1:
                buf = sock.recv(4096)
                if not buf:
                    break
                data += buf
        except socket.error as e:
            self.log.error("Error retrieving HAProxy stats. %s", e)
            return []

        return data.strip().split('\n')

    def _generate_headings(self, row):
        headings = {}
        for index, heading in enumerate(row):
            headings[index] = self._sanitize(heading)
        return headings

    def _collect(self, section=None):
        """
        Collect HAProxy Stats
        """
        if self.config['method'] == 'http':
            csv_data = self.http_get_csv_data(section)
        elif self.config['method'] == 'unix':
            csv_data = self.unix_get_csv_data()
        else:
            self.log.error("Unknown collection method: %s",
                           self.config['method'])
            csv_data = []

        data = list(csv.reader(csv_data))
        headings = self._generate_headings(data[0])
        section_name = section and self._sanitize(section.lower()) + '.' or ''

        for row in data:
            if ((self._get_config_value(section, 'ignore_servers') and
                 row[1].lower() not in ['frontend', 'backend'])):
                continue

            part_one = self._sanitize(row[0].lower())
            part_two = self._sanitize(row[1].lower())
            metric_name = '%s%s.%s' % (section_name, part_one, part_two)

            for index, metric_string in enumerate(row):
                if index < 2:
                    continue

                metric_string_ok = False
                try:
                    metric_value = float(metric_string)
                except ValueError:
                    if not metric_string:
                        continue
                    metric_string_ok = True
                    metric_value = 1

                if metric_string_ok:
                    stat_name = '%s.%s.%s' % (metric_name, headings[index],
                                              self._sanitize(metric_string))
                else:
                    stat_name = '%s.%s' % (metric_name, headings[index])

                stat_name = '%s.%s' % (metric_name, headings[index])
                self.publish(stat_name, metric_value, metric_type='GAUGE')

    def collect(self):
        if 'servers' in self.config:
            if isinstance(self.config['servers'], list):
                for serv in self.config['servers']:
                    self._collect(serv)
            else:
                self._collect(self.config['servers'])
        else:
            self._collect()

    def _sanitize(self, s):
        """Sanitize the name of a metric to remove unwanted chars
        """
        return re.sub('[^\w-]', '_', s)
