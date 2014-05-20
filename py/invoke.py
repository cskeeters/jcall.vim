import sys
import os
import re
import dbm
import marshal
from jcall import argtrans
from jcall import splitinvoke
from jcall import JavadParser
from jcall import check_in

def getsuperclasses(classname):
    try:
        return marshal.loads(supers[classname])
    except KeyError:
        print "Warning: Could not find superclasses for %s" % classname
        return []

def getoutput(cmd):
    pipe = os.popen(cmd, 'r', 4096)
    output = pipe.read().strip()
    pipe.close()
    return output

def find_signature(javad_path, acceptable_classnames, invokation):
    target_classname, target_method = splitinvoke(invokation.method_signature)
    #print "Searching %s for %s.%s" % (javad_path, target_classname, target_method)

    if not check_in(javad_path, target_method):
        return

    parser = JavadParser()
    parser.parse_path(javad_path)

    if parser.classdef.name in acceptable_classnames:
        for method in parser.get_methods():
            cur_specific_signature = splitinvoke(method.signature)[1]
            #print cur_specific_signature, target_method
            if cur_specific_signature == target_method:
                package = parser.classdef.package.replace('.', '/')
                sourcefilename = parser.source
                if len(method.linerefs) > 0:
                    print '%s:%s:%d' % (package, sourcefilename, method.linerefs[0].lineno-1)


def search_for(invokation):
    if invokation.type in ['virtual', 'interface']:
        acceptable_classnames = [invokation.classname] + getsuperclasses(invokation.classname)
    else:
        acceptable_classnames = [invokation.classname]

    for root, dirs, files in os.walk('/tmp/jcall'+builddir):
        for name in files:
            if name.endswith('.javap'):
                find_signature(os.path.join(root, name), acceptable_classnames, invokation)


def get_next_invoke(method, index, target_name):

    cur_index = 9999999999
    cur_invokation = None
    for invokation in method.invokations:
        if invokation.index >= index and invokation.index < cur_index and invokation.name == target_name:
            cur_index = invokation.index
            cur_invokation = invokation

    if cur_invokation == None:
        print "Could not find method invokation with name", target_name
        sys.exit(1)
    return cur_invokation

def print_invokes(classfile, builddir, target_filename, target_lineno, target_name):
    lines = getoutput("/usr/bin/javap -classpath '%s' -c -l -private '%s' " % (builddir, classfile)).split('\n')
    parser = JavadParser()
    for line in lines:
        parser.parse_line(line)

    if parser.source == target_filename:
        for method in parser.get_methods():
            if method.has_key('linerefs'):
                for lineref in method.linerefs:
                    if lineref.lineno == target_lineno:
                        #print "match line number at ", parser.source, lineref.lineno, lineref.index
                        invokation = get_next_invoke(method, lineref.index, target_name)
                        search_for(invokation)


def getPackageName(filename):
    packagep = re.compile(".*package +(.*) *;.*")
    for line in open(filename):
        m = packagep.match(line)
        if m != None:
            return m.group(1)
    return None


def get_class_files(builddir, filename, packagepath):
    sourcename, sourceext = os.path.splitext(filename)
    classpattern=sourcename
    if packagepath != '':
        classpattern = packagepath+"/"+sourcename

    return getoutput('cd %s; find . -wholename "./%s*.class" -type f | sed -e "s/..\(.*\)/\\1/" ' % (builddir, classpattern)).split('\n')

if __name__ == "__main__":

    filepath = sys.argv[1]
    filename = os.path.basename(filepath)
    lineno = int(sys.argv[2])
    target_name = sys.argv[3]
    builddir = os.path.normpath(sys.argv[4])
    packagename = getPackageName(filepath)
    if packagename == None:
        packagename = ''
    packagepath = packagename.replace('.', '/')

    db = dbm.open('/tmp/jcall'+builddir+'/linenos', 'c')
    supers = dbm.open('/tmp/jcall'+builddir+'/supers', 'c')

    for classfile in get_class_files(builddir, filename, packagepath):
        classname, classext = os.path.splitext(classfile)
        print_invokes(classname, builddir, filename, lineno, target_name)
