#!/usr/bin/env python2.6

# Copyright 2010 Lisa Glendenning
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>

r"""Google Apps Email Migration python client library.

Notes: 

- This Google API is only available to Google Apps Premier, 
  Education, and Partner Edition domains, and cannot be used for 
  migration into Google Apps Standard Edition email or Gmail accounts.

- API Reference: http://code.google.com/googleapps/domain/email_migration/developers_guide_protocol.html

History:

- April 29, 2010 Lisa Glendenning (lglenden@cs.washington.edu): Created

"""

##############################################################################
##############################################################################

import datetime, time, sys
import xml.dom.minidom
from xml.etree import ElementTree
import httplib, urllib, urllib2

##############################################################################
##############################################################################

# Per-request timeout
HTTP_TIMEOUT = 10.0

# base64 encoding is deprecated
ENCODING = 'utf-8'

##############################################################################
# Common headers
##############################################################################

def agent_header(text=''):
    return ('User-Agent', text)

def content_header(type):
    return ('Content-Type', type)

def length_header(body):
    return ('Content-Length', str(len(body)))

##############################################################################
##############################################################################

class Multipart(object):
    r"""Multipart Content Type."""
    
    CRLF = '\r\n'

    def __init__(self, subtype, headers=None):
        self.subtype = subtype
        self.headers = headers
        self.parts = []
        self.boundary = str(int(time.time()))
        if self.headers:
            self.headers.append(content_header(self.content_type))
        return
    
    content_type = property(lambda self: 'multipart/%s; boundary=%s' % (self.subtype, self.boundary))
    
    def append(self, headers, body):
        self.parts.append((headers, body))

    def encode_part(self, headers, body):
        part_boundary = '--' + self.boundary
        lines = [part_boundary]
        lines.extend([': '.join(h) for h in headers])
        lines.append('')
        lines.append(body)
        return lines
        
    def __str__(self):
        lines = []
        if self.headers:
            lines.extend([': '.join(h) for h in self.headers])
            lines.append('')
        for part in self.parts:
            lines.extend(self.encode_part(*part))
        lines.append('--%s--' % self.boundary)
        lines.append('')
        return self.CRLF.join(lines)
    
##############################################################################
# Sample email for testing
##############################################################################

EMAIL_TIME_FORMAT = '%a, %d %b %Y %H:%M:%S %z'

SAMPLE_MESSAGE_LINES = ['This is a test mail using multipart HTTP requests for Email Migration API.',
                        '',
                        'EOM']
SAMPLE_MESSAGE_PARTS = [([('Content-Type', 'text/plain; charset=ISO-8859-1')],
                         Multipart.CRLF.join(SAMPLE_MESSAGE_LINES)),
                        ([('Content-Type', 'text/html; charset=ISO-8859-1')],
                         ('%s<br>' % Multipart.CRLF).join(['<b>%s</b>' % l for l in SAMPLE_MESSAGE_LINES]))]
SAMPLE_HEADERS = [('MIME-Version', '1.0'),
                  ('Date', datetime.datetime.utcnow().strftime(EMAIL_TIME_FORMAT)),
                  ('To', 'You <you@example.com>'),
                  ('From', 'Migration <migration@example.com>'),
                  ('Subject', 'Email Migration Test Message')]

SAMPLE_EMAIL = Multipart('alternative', SAMPLE_HEADERS)
for part in SAMPLE_MESSAGE_PARTS:
    SAMPLE_EMAIL.append(*part)

##############################################################################
# Google authentication
##############################################################################

# For authentication
AUTH_SERVER = 'https://www.google.com'
AUTH_URL = 'accounts/ClientLogin'
AUTH_SERVICE = 'apps'
AUTH_ACCOUNT_TYPE = 'HOSTED'
AUTH_CONTENT_TYPE = 'application/x-www-form-urlencoded'

def encode_authentication_body(email, password):
    account = AUTH_ACCOUNT_TYPE
    service = AUTH_SERVICE
    fields = { 'Email' : email,
               'Passwd' : password,
               'accountType' : account,
               'service' : service
             }
    body = urllib.urlencode(fields)
    return body

def authenticate(body):
    r""" Returns an authentication token if successful. 
    
    Tokens expire after 24 hours.
    """
    url = '%s/%s' % (AUTH_SERVER, AUTH_URL)
    request = urllib2.Request(url, body)
    request.add_header(*agent_header())
    request.add_header(*content_header(AUTH_CONTENT_TYPE))
    
    response = urllib2.urlopen(request, timeout=HTTP_TIMEOUT)
    
    body = response.read()
    for line in body.splitlines():
        tokens = line.split('Auth=')
        if len(tokens) > 1:
            assert len(tokens) == 2, line
            token = tokens[1]
            break
    else:
        raise httplib.HTTPException('%s\n%s' % (response.info(), body))
    return token

def auth_header(token):
    return ('Authorization', 'GoogleLogin auth=%s' % token)

##############################################################################
# Email Migration API
##############################################################################

MAIL_FLAGS = [2**i for i in xrange(6)]
MAIL_DRAFT, MAIL_INBOX, MAIL_SENT, MAIL_STARRED, MAIL_TRASH, MAIL_UNREAD = MAIL_FLAGS
MAIL_PROPERTIES = { MAIL_DRAFT : 'IS_DRAFT',
                    MAIL_INBOX : 'IS_INBOX',
                    MAIL_SENT : 'IS_SENT',
                    MAIL_STARRED : 'IS_STARRED',
                    MAIL_TRASH : 'IS_TRASH',
                    MAIL_UNREAD : 'IS_UNREAD' }

# For XML schema
XML_NAMESPACE = 'http://schemas.google.com/apps/2006'
APP_NAMESPACE = 'apps'
MAIL_PROPERTY = 'mailItemProperty'
LABEL_PROPERTY = 'label'

def encode_mail_schema(properties=None, labels=None):
    entry = ElementTree.Element('entry')
    entry.set('xmlns', 'http://www.w3.org/2005/Atom')
    entry.set('xmlns:apps', XML_NAMESPACE)
    
    category = ElementTree.SubElement(entry, 'category')
    category.set('scheme', 'http://schemas.google.com/g/2005#kind')
    category.set('term', 'http://schemas.google.com/apps/2006#mailItem')
    
    content = ElementTree.SubElement(entry, 'atom:content')
    content.set('xmlns:atom', 'http://www.w3.org/2005/Atom')
    content.set('type', MAIL_CONTENT_TYPE)

    if properties:
        for flag in MAIL_FLAGS:
            if flag & properties:
                property = ElementTree.SubElement(entry, '%s:%s' % (APP_NAMESPACE, MAIL_PROPERTY))
                property.set('xmlns:apps', XML_NAMESPACE)
                property.set('value', MAIL_PROPERTIES[flag])
    
    if labels:
        for l in labels:
            label = ElementTree.SubElement(entry, '%s:%s' % (APP_NAMESPACE, LABEL_PROPERTY))
            label.set('xmlns:apps', XML_NAMESPACE)
            label.set('labelName', l)
            
    text = ElementTree.tostring(entry, encoding=ENCODING)
    xmldoc = xml.dom.minidom.parseString(text)
    return xmldoc.toxml(encoding=ENCODING)

##############################################################################

SCHEMA_CONTENT_TYPE = 'application/atom+xml'
MAIL_CONTENT_TYPE = 'message/rfc822'

def post_mail(url, token, schema, message):
    multipart = Multipart('related')
    multipart.append([content_header(SCHEMA_CONTENT_TYPE)], schema)
    multipart.append([content_header(MAIL_CONTENT_TYPE)], message)
    body = str(multipart)
    
    request = urllib2.Request(url, body)
    request.add_header(*auth_header(token))
    request.add_header(*content_header(multipart.content_type))
    request.add_header(*length_header(body))

    try:
        response = urllib2.urlopen(request, timeout=HTTP_TIMEOUT)
    except urllib2.URLError as e:
        sys.stderr.write('%s: %s:\n%s\%s\n' % (url, e, request.headers, request.data))
        raise
    else:
        return response
    
##############################################################################
# Convenience front end
##############################################################################

API_VERSION = '2.0'
APPS_SERVER = 'https://apps-apis.google.com'

class EmailMigrationService(object):
    r"""Interface to email migration functions.
    
    Example Usage:
    
        >>> import migration
        >>> my_email = 'user@domain.com'
        >>> my_password = 'secret'
        >>> service = migration.EmailMigrationService(my_email, my_password)
        >>> service.authenticate()
        >>> message = str(migration.SAMPLE_EMAIL)
        >>> properties = migration.MAIL_INBOX | migration.MAIL_UNREAD
        >>> labels = ['testing']
        >>> failed = service.upload_messages([message], properties, labels)
        >>> for msg, reason in failed:
        ...   print "Error:", reason
        ...   print msg
    
    """
    
    FEED = '/a/feeds/migration/%(version)s/%(domain)s/%(username)s/mail'
    
    def __init__(self, email, password):
        r"""Initialize service with authentication parameters.
        
        Args:
            email: email address of the domain administrator or user
            password: password for the domain administrator or user
            
        """
        self.email = email
        self.password = password
        self.token = None
    
    def authenticate(self):
        r"""Request a fresh authentication token."""
        request = encode_authentication_body(self.email, self.password)
        self.token = authenticate(request)
    
    def upload_messages(self, 
                        messages, 
                        properties=None, 
                        labels=None, 
                        username=None, 
                        domain=None):
        r"""Issues post requests for a sequence of emails.
        
        Args:
            message: sequence of strings
            properties: optional bitwise combination of MAIL_FLAGS
            labels: optional sequence of strings
            username: optional Google username (default is from the authenticating email)
            domain: optional Google domain (default is from the authenticating email)
        
        Returns:
            A sequence of 2-tuples of type (string, Exception).
            Each tuple is a message that failed to upload
            and the exception that was generated from that request.
        
        Raises:
            RuntimeError
        
        """
        if not self.token:
            raise RuntimeError('Authentication required first')
        if not username:
            username = self.email.split('@')[0]
        if not domain:
            domain = self.email.split('@')[1]
        feed = self.FEED % { 'version' : API_VERSION,
                             'username' : username,
                             'domain' : domain }
        url = '%s%s' % (APPS_SERVER, feed)
        schema = encode_mail_schema(properties, labels)
        failed = []
        for message in messages:
            try:
                response = post_mail(url, self.token, schema, message)
            except urllib2.URLError as e:
                failed.append((message, e))
        return failed
        
##############################################################################
##############################################################################

