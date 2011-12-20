#!/usr/bin/env python2.6

# Copyright (c) 2009 by Joseph Devietti (devietti@cs.washington.edu).

# This file is part of the tbird2gmail program.

# Tbird2gmail is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Tbird2gmail is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Tbird2gmail.  If not, see <http://www.gnu.org/licenses/>.

r"""Sample script to upload mbox files to Google Apps.

Requires migration.py from http://github.com/lisaglendenning/google-apps-email-migrate

History:

- April 29, 2010 Lisa Glendenning (lglenden@cs.washington.edu):
  Modified from http://www.cs.washington.edu/homes/devietti/tbird2gmail/tbird2gmail.py

"""

##############################################################################
##############################################################################

import os, os.path, sys, socket, time, optparse, email, mailbox

import migration

##############################################################################
##############################################################################

OUTPUT_TAG = "mbox2gdata"
FOLDER_DELIM = '-'
FAILED_PREFIX = "%s%sfailed" % (OUTPUT_TAG,FOLDER_DELIM)
FAILURE_HEADER = 'X-%s-Failure' % OUTPUT_TAG
UNLABELED_FOLDER = 'all'
FLAGS = { 'INBOX' : migration.MAIL_INBOX,
          'UNREAD' : migration.MAIL_UNREAD,
          'STARRED' : migration.MAIL_STARRED,
          'TRASH' : migration.MAIL_TRASH,
          'DRAFT' : migration.MAIL_DRAFT,
          'SENT' : migration.MAIL_SENT }

##############################################################################
##############################################################################

def upload_test(service, options):
    message = str(migration.SAMPLE_EMAIL)
    properties = migration.MAIL_UNREAD | migration.MAIL_INBOX | migration.MAIL_STARRED
    labels = [OUTPUT_TAG]
    messages = message,
    if options.verbose:
        print "Uploading sample message:"
        print message
    if not options.dryrun:
        for failed, why in service.upload_messages(messages, properties, labels):
            sys.stderr.write('Error:%s\n%s\n' % (why, failed))

##############################################################################

def upload_folder(path, service, options):
    sys.stdout.write("Opening mbox file: %s\n" % path)
        
    # extract properties and labels from file name
    folder = os.path.basename(path).rsplit('.', 1)[0]
    labels = None
    properties = 0
    if folder != UNLABELED_FOLDER:
        labels = folder.split(FOLDER_DELIM)
        i = 0
        while i < len(labels):
            label = labels[i]
            if label in FLAGS:
                flag = FLAGS[label]
                properties |= flag
                if options.verbose:
                    print "Flag:", migration.MAIL_PROPERTIES[flag]
                del labels[i]
            else:
                if options.verbose:
                    print "Label:", label
                i += 1
        
    failed_file = '%s%s%s.mbox' % (FAILED_PREFIX,
                                   FOLDER_DELIM, 
                                   folder)
    if options.verbose:
        print 'Messages that fail to upload will be written to:', failed_file
    failed_mbox = None
            
    mbox = mailbox.mbox(path)
    total = len(mbox)
    progress_format = 'Message %d/' + str(total) + ': (%d kB) ...'
    count = 0
    total_size = 0
    failed = None
    for mailkey in mbox.iterkeys():
        count += 1
        message = mbox.get_string(mailkey)
        size = len(message) / 1000
        if options.verbose:
            print progress_format % (count, size)
        
        if not options.dryrun:
            messages = message,
            failed = service.upload_messages(messages, properties, labels)
            if failed and failed_mbox is None:
                failed_mbox = mailbox.mbox(failed_file, create=True)
            for msg, why in failed:
                if options.verbose:
                    print 'ERROR:', str(why)
                obj = email.message_from_string(msg)
                obj[FAILURE_HEADER] = str(why)
                failed_mbox.add(obj)
                failed_mbox.flush()
        if not failed:
            total_size += size
    
    if options.verbose:
        print 'Successful data upload: %d kB' % total_size
        
##############################################################################

def upload(options):
    service = migration.EmailMigrationService(options.email, options.password)
    service.authenticate()
    
    if options.test:
        upload_test(service, options)
        return
    
    path = options.input
    folders = []
    if os.path.isdir(path):
        for file in os.listdir(path):
            if not file.startswith(FAILED_PREFIX) and file.endswith('.mbox'):
                folders.append(os.path.join(path, file))
    elif os.path.isfile(path):
        folders.append(path)
    else:
        raise RuntimeError('Input path must be a directory or file: %s' % path)

    for path in folders:
        upload_folder(path, service, options)

##############################################################################
##############################################################################

def main(argv):
    usage = "%prog [options] GOOGLE_EMAIL GOOGLE_PASSWORD..."
    description="""Uploads emails from a set of mbox files to Google Apps.  The '-i' option is
used to specify either the filename of an mbox file, or a directory containing
mbox files. The default behavior is to look for .mbox files in the 
current working directory.
mbox2gdata uses a naming convention for .mbox files.  The name of the file
must be either the keyword 'all', or one or more labels 
separated by the character '-'.  Some labels
are reserved for Google Mail Properties:
INBOX, STARRED, UNREAD, TRASH, DRAFT, SENT. The keyword 'all' will result
in those messages being uploaded without any labels or properties.
For example: All messages in the file 'INBOX-STARRED-priority.mbox' will
be uploaded to your Inbox, starred, and labeled with 'priority'.
"""

    optparser = optparse.OptionParser(usage=usage, description=description)
    optparser.add_option('-i',
                         '--input',
                         metavar='PATH',
                         dest="input",
                         default = os.getcwd(),
                         help='mbox file, or directory containing mbox files')

    # testing/debugging
    optparser.add_option('-t',
                         "--test",
                          dest="test",
                          default=False, 
                          action="store_true",
                          help="Upload a single test email to your Inbox. The email will be starred and unread." )
    optparser.add_option('-v',
                          "--verbose",
                          dest="verbose",
                          default=False, 
                          action="store_true",
                          help="Turn on debugging output" )
    optparser.add_option('-d',
                          "--dry-run", 
                          dest="dryrun",
                          default=False, 
                          action="store_true",
                          help="Execute the program without side effects." )
    
    options, args = optparser.parse_args(argv)
    if len(args) != 3:
        optparser.error("Incorrect number of required arguments")
    
    prog, email, password = args
    assert 1 == email.count('@'), 'Malformed email address: %s' % email
    options.email = email
    options.password = password
    
    if not os.path.isabs(options.input):
        options.input = os.path.abspath(options.input)
        if not os.path.exists(options.input):
            optparser.error("Nonexistent path: %s" % options.input)
    
    upload(options)

##############################################################################
##############################################################################

if __name__ == '__main__':
    main(sys.argv)

##############################################################################
##############################################################################

