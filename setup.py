#!/usr/bin/env python
#-*- coding: utf-8 -*-
import os
import re
import sys
import shutil
import hashlib
import urllib2
from zipfile import ZipFile
from distutils.core import setup

######################################################################
# Temporary fix to https://github.com/globaleaks/GlobaLeaks/issues/572
#                  https://github.com/habnabit/txsocksx/issues/5
from distutils import version
version.StrictVersion = version.LooseVersion
######################################################################

from globaleaks import __version__

def pip_to_requirements(s):
    """
    Change a PIP-style requirements.txt string into one suitable for setup.py
    """
    m = re.match('(.*)([>=]=[.0-9a-zA-Z]*).*', s)
    if m:
        return '%s (%s)' % (m.group(1), m.group(2))
    return s.strip()

if not sys.version_info[:2] == (2, 7):
    print "Error, GlobaLeaks is tested only with python 2.7"
    print "https://github.com/globaleaks/GlobaLeaks/wiki/Technical-requirements"
    raise AssertionError

glclient_path = 'glclient-v'+__version__
def download_glclient():
    glclient_url = "https://globaleaks.org/builds/GLClient/"+glclient_path+".zip"
    print "[+] Downloading glclient from %s" % glclient_url

    o = open('glclient.zip', 'w+')
    f = urllib2.urlopen(glclient_url)
    o.write(f.read())
    o.close()
    print "    ...done."

def verify_glclient():
    print "[+] Checking GLClient hash..."
    glclient_hash = "562901470fd5d3beab6acff68a9f5b2fb77c5036ceff798444ef25df"
    with open('glclient.zip') as f:
        h = hashlib.sha224(f.read()).hexdigest()
        if not h == glclient_hash:
            raise Exception("%s != %s" % (h, glclient_hash))
    print "    ...success."

def uncompress_glclient(glclient_path):
    print "[+] Uncompressing GLClient..."
    zipfile = ZipFile('glclient.zip')
    zipfile.extractall()
    os.unlink('glclient.zip')
    shutil.move(glclient_path, 'glclient')
    print "    ...done."

# remind ask to evilaliv3: why is here this function ? 
def build_glclient():
    print "[+] Building GLClient..."
    os.chdir(glclient_path)
    os.system("npm install -d")
    os.system("grunt build")
    os.chdir('..')
    print "    ...done."

def get_requires():
    with open('requirements.txt') as f:
        requires = map(pip_to_requirements, f.readlines())
        return requires


if not os.path.isdir(os.path.abspath(os.path.join(os.path.dirname(__file__), 'glclient'))):
    download_glclient()
    verify_glclient()
    uncompress_glclient(glclient_path)
glclient_path = 'glclient'

data_files = [
    ('/usr/share/globaleaks/glclient', [
    os.path.join(glclient_path, 'index.html'),
    os.path.join(glclient_path, 'styles.css'),
    os.path.join(glclient_path, 'scripts.js'),
    ]),
    ('/usr/share/globaleaks/glclient/fonts', [
    os.path.join(glclient_path, 'fonts', 'glyphicons-halflings-regular.eot'),
    os.path.join(glclient_path, 'fonts', 'glyphicons-halflings-regular.svg'),
    os.path.join(glclient_path, 'fonts', 'glyphicons-halflings-regular.ttf'),
    os.path.join(glclient_path, 'fonts', 'glyphicons-halflings-regular.woff'),
    ]),
    ('/usr/share/globaleaks/glclient/img', [
    os.path.join(glclient_path, 'img', 'loading.gif'),
    ]),
    ('/usr/share/globaleaks/glclient/l10n', [
    os.path.join(glclient_path, 'l10n', 'ar.json'),
    os.path.join(glclient_path, 'l10n', 'bg.json'),
    os.path.join(glclient_path, 'l10n', 'cs.json'),
    os.path.join(glclient_path, 'l10n', 'de.json'),
    os.path.join(glclient_path, 'l10n', 'en.json'),
    os.path.join(glclient_path, 'l10n', 'es.json'),
    os.path.join(glclient_path, 'l10n', 'fr.json'),
    os.path.join(glclient_path, 'l10n', 'hu_HU.json'),
    os.path.join(glclient_path, 'l10n', 'it.json'),
    os.path.join(glclient_path, 'l10n', 'nl.json'),
    os.path.join(glclient_path, 'l10n', 'pt_BR.json'),
    os.path.join(glclient_path, 'l10n', 'ru.json'),
    os.path.join(glclient_path, 'l10n', 'sr_RS.json'),
    os.path.join(glclient_path, 'l10n', 'sr_RS@latin.json'),
    os.path.join(glclient_path, 'l10n', 'vi.json')
    ]),
    ('/usr/share/globaleaks/glbackend',  [
    'requirements.txt',
    'staticdata/favicon.ico',
    'staticdata/robots.txt',
    'staticdata/globaleaks_logo.png',
    'staticdata/default-profile-picture.png'
    ])
]

setup(
    name="globaleaks",
    version = __version__,
    author="Random GlobaLeaks developers",
    author_email = "info@globaleaks.org",
    url="https://globaleaks.org/",
    package_dir={'globaleaks': 'globaleaks'},
    package_data = {'globaleaks': ['db/sqlite.sql', 'db/default_TNT.txt',
                                   'db/default_CNT.txt', 'db/default_FNT.txt']},
    packages=['globaleaks', 'globaleaks.db', 'globaleaks.handlers',
        'globaleaks.jobs', 'globaleaks.plugins', 'globaleaks.rest',
        'globaleaks.utils', 'globaleaks.third_party', 'globaleaks.third_party.rstr'],
    data_files=data_files,
    scripts=["bin/globaleaks", "scripts/glclient-build", 'bin/gl-reset-password', 'bin/gl-fix-permissions'],
    requires = get_requires(),
)
