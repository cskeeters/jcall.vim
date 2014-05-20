import sys
import os
import re
import dbm
import marshal
from jcall import argtrans
from jcall import JavadParser

def getoutput(cmd):
    pipe = os.popen(cmd, 'r', 4096)
    output = pipe.read().strip()
    pipe.close()
    return output


def get_closest(classfile, builddir, target_filename, target_lineno):
    parser = JavadParser()
    parser.parse_path("/tmp/jcall"+builddir+"/"+classfile+".javap")

    cur_method=None # closest match to targets: filename:lineno
    cur_index=None
    cur_lineno=-1

    if parser.source == target_filename:
        for method in parser.get_methods():
            if method.has_key('linerefs'):
                for lineref in method.linerefs:
                    if (lineref.lineno > cur_lineno) and (lineref.lineno <= target_lineno):
                        cur_method = method.signature
                        cur_index = lineref.index
                        cur_lineno = lineref.lineno

    return (cur_method, cur_index, cur_lineno)

def find_in_classfile(classfile, builddir, target_classname, target_methodname):
    parser = JavadParser()
    parser.parse_path("/tmp/jcall"+builddir+"/"+classfile+".javap")

    if parser.get_classdef().name != target_classname:
        return None
    signatures = []
    for method in parser.get_methods():
        if method.name == target_methodname:
            signatures.append(method.signature)
    return signatures


def getPackageName(filename):
    packagep = re.compile(".*package +(.*) *;.*")
    for line in open(filename):
        m = packagep.match(line)
        if m != None:
            return m.group(1)
    return None

def getClassName(filename):
    classp = re.compile(".*(class|interface) +([a-zA-Z][a-zA-Z0-9_\-]*).*")
    for line in open(filename):
        m = classp.match(line)
        if m != None:
            return m.group(2)
    return None

def getMethod(filename, lineno):
    f = open(filename)
    for i in xrange(1,lineno):
        trash = f.readline()
    line = f.readline()

    methodp = re.compile(".* (.*) ([a-zA-Z][a-zA-Z0-9_\-]*) *\((.*)\)")
    m = methodp.match(line)
    if m != None:
        return m.group(2)
    return None

# tries to parse the source code inself (gasp) and return a method signature
def get_method_signatures(builddir, filepath, lineno, packagepath):
    packagename = getPackageName(filepath)
    classname = getClassName(filepath)
    if packagename != None:
        classname = packagename+"."+classname
    #print "ClassName:",classname
    methodname = getMethod(filepath, lineno)
    #print "MethodName:",methodname

    signatures = []
    for classfile in get_class_files(builddir, os.path.basename(filepath), packagepath):
        classname, classext = os.path.splitext(classfile)
        signatures += find_in_classfile(classname, builddir, classname, methodname)

    return signatures

def get_class_files(builddir, filename, packagepath):
    sourcename, sourceext = os.path.splitext(filename)
    classpattern=sourcename
    if packagepath != '':
        classpattern = packagepath+"/"+sourcename

    return getoutput('cd %s; find . -wholename "./%s*.class" -type f | sed -re "s/..(.*)/\\1/" ' % (builddir, classpattern)).split('\n')

if __name__ == "__main__":

    filepath = sys.argv[1]
    filename = os.path.basename(filepath)
    lineno = int(sys.argv[2])
    builddir = os.path.normpath(sys.argv[3])
    packagename = getPackageName(filepath)
    if packagename == None:
        packagename = ''
    packagepath = packagename.replace('.', '/')

    cur_method=None # closest match to targets: filename:lineno
    cur_index=None
    cur_lineno=-1

    for classfile in get_class_files(builddir, filename, packagepath):
        classname, classext = os.path.splitext(classfile)
        (method, index, lno) = get_closest(classname, builddir, filename, lineno+2)
        #print cur_method, cur_index, cur_lineno
        #print method, index, lno
        if (lno > cur_lineno) and (lno <= lineno+2):
            #print lno, cur_lineno, lineno
            cur_method = method
            cur_index = index
            cur_lineno = lno
    if cur_lineno != -1:
        print cur_method
    else:
        signatures = get_method_signatures(builddir, filepath, lineno, packagepath)
        for signature in signatures:
            print signature
