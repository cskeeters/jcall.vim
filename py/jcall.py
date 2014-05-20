import os
import sys
import re
import dbm
import marshal
import threading

source_pattern=re.compile('^Compiled from "(.*)"')
class_pattern=re.compile('^(public|private)? ?(abstract)? ?(final)? ?(class|interface) ([^ ]*) ?(extends ([^ ]+))? ?(implements ([^ ]+))?{$')
constructor_pattern=re.compile('^(public|private|protected)? ?([^ ]+)\((.*)\)(.*throws (.*))?;$')
method_pattern=re.compile('^(public|private|protected)? ?(static)? ?(synchronized)? ?(abstract)? ?([^ ]+) ([^ ]+)\((.*)\)(.*throws (.*))?;$')
invoke_pattern=re.compile(' *([0-9]+):.*invoke(virtual|special|static|interface).*Method (.*)')
static_pattern=re.compile('^static {};')
lineno_pattern=re.compile(' *line ([0-9]+): *([0-9]+)')

sourcefile=None
classname=None
method=None

type_pattern=re.compile('(void|boolean|byte|int|long|float|double)(\[\])?')
object_pattern=re.compile('(.*)(\[\])?')

class dotdict:
    def __init__(self, dictionary={}):
        self.__dict__ = dict(dictionary)
    def __setitem__(self, attr, value):
        setattr(self, attr, value)
    def __getitem__(self, attr):
        return getattr(self, attr)
    def __repr__(self):
        return repr(self.__dict__)
    def has_key(self, key):
        return self.__dict__.has_key(key)

class JavapError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

def extract_name(method_signature):
    pre, args = method_signature.split(":")
    return pre.split(".")[-1]

# returns (type, object) for parsed line
class JavadParser:
    def __init__(this):
        this.source = None
        this.classdef = None
        this.methods = []

    def get_classdef(this):
        return this.classdef

    def get_source(this):
        return this.source

    def get_methods(this):
        return this.methods


    def parse_handle(this, file):
        for line in file:
            this.parse_line(line)

    def parse_path(this, path):
        file = open(path)
        try:
            this.parse_handle(file)
        except JavapError, e:
            print "Error parsing %s" % path
            print e.value
        file.close()


    def parse_line(this, line):
        m=source_pattern.match(line)
        if m != None:
            this.source = m.group(1)

        m=class_pattern.match(line)
        if m != None:
            this.classdef = dotdict()
            this.classdef.access = m.group(1)
            this.classdef.abstract = m.group(2)
            this.classdef.final = m.group(3)
            this.classdef.type = m.group(4)
            this.classdef.name = m.group(5)
            package_sep_index = this.classdef.name.rfind('.')
            if package_sep_index != -1:
                this.classdef.package = this.classdef.name[0:package_sep_index]
            else:
                this.classdef.package = ''
            this.classdef.extends = m.group(7)
            implements = m.group(9)
            if implements == None:
                this.classdef.implements = []
            else:
                this.classdef.implements = implements.split(",")
            #print "name:", this.classdef.name
            #print "Extends:", this.classdef.extends
            #print "Implements:", this.classdef.implements

        m=static_pattern.match(line)
        if m != None:
            method = dotdict()
            method.name = 'static'
            method.signature = '%s.static' % (classname)
            method.invokations = []
            this.methods.append(method)

        m=method_pattern.match(line)
        if m != None:
            method = dotdict()
            method.access = m.group(1)
            method.static = m.group(2)
            method.synchronized = m.group(3)
            method.abstract = m.group(4)
            method.return_type = m.group(5)
            method.name = m.group(6)
            method.arguments = m.group(7).split(',')
            throws = m.group(9)
            if throws == None:
                method.throws = []
            else:
                method.throws = throws.split(',')

            arguments = map(str.strip, method.arguments)
            arguments = map(argtrans, arguments)
            arguments = ''.join(arguments)
            method.signature = "%s.%s:(%s)%s" % (this.classdef.name, method.name, arguments, argtrans(method.return_type))
            method.invokations = []

            this.methods.append(method)

        m=constructor_pattern.match(line)
        if m != None:
            method = dotdict()
            method.access = m.group(1)
            method.static = False
            method.synchronized = False # FIX?
            method.abstract = False
            method.return_type = 'void'
            method.name = '"<init>"' #m.group(2)
            method.arguments = m.group(3).split(',')
            throws = m.group(5)
            if throws == None:
                method.throws = []
            else:
                method.throws = throws.split(',')

            arguments = map(str.strip, method.arguments)
            arguments = map(argtrans, arguments)
            arguments = ''.join(arguments)
            method.signature = "%s.%s:(%s)V" % (this.classdef.name, method.name, arguments) # const always shows void return
            method.invokations = []

            this.methods.append(method)

        m=invoke_pattern.match(line)
        if m != None:
            invokation = dotdict()
            invokation.index = int(m.group(1))
            invokation.type = m.group(2)
            invokation.method_signature = m.group(3) # what I'm calling

            if invokation.method_signature.find(".") == -1:
                invokation.classname = this.classdef.name
                invokation.method = invokation.method_signature
                invokation.method_signature = "%s.%s" % (invokation.classname,invokation.method)
            else:
                invokation.method_signature = invokation.method_signature.replace('/', '.')
                invokation.classname, invokation.method = splitinvoke(invokation.method_signature)

            invokation.name = extract_name(invokation.method_signature)

            if len(this.methods) == 0:
                raise JavapError("Invocation without method definition")

            this.methods[-1].invokations.append(invokation)

        m=lineno_pattern.match(line)
        if m != None:
            if len(this.methods) == 0:
                raise JavapError("%s Matched lineno_pattern without method in %s" % (line, this.source))

            method = this.methods[-1]

            if not method.has_key('linerefs'):
                method.linerefs = []

            lineref = dotdict()
            lineref.lineno=int(m.group(1))
            lineref.index=int(m.group(2))
            method.linerefs.append(lineref)
            #print '%s:%s -> %s:%s' % (method, m.group(2), sourcefile, m.group(1))

# Translates 'byte' into 'B' and 'java.lang.Object' into 'Ljava.lang.object;'
def argtrans(a):
    if a == '':
        return ''
    m=type_pattern.match(a)
    if m != None:
        type = m.group(1)[0].upper()
        if m.group(1) == 'long':
            type = "J"
        if m.group(1) == 'boolean':
            type = "Z"
        if m.group(2) == '[]':
            type='['+type
        return type
    m=object_pattern.match(a)
    if m != None:
        type = "L"+m.group(1)
        if m.group(2) == '[]':
            type+='['
        return type+";"
    raise Exception("could not translate argument "+a)

# Returns Main.java:34 for (my.Main.main:(I[C)V, 0)
def find_lineno(method, index):
    #print "Finding %s:%s" % (method, index)
    try:
        index_list = marshal.loads(db[method])
        curindex = -1
        cursource = None
        for i, source, lineno in index_list:
            #print i, source
            if i <= index:
                if i > curindex:
                    curindex = i;
                    cursource = (source, lineno)
        return cursource
    except KeyError:
        return "Error finding linenos for %s" % method

# Gets list of class (or interface) names that extend or implement classname
def getsubclasses(classname):
    try:
        return marshal.loads(classsig[classname])
    except KeyError:
        return []

# seperates classname from methodname
def splitinvoke(method_signature):
    ci = method_signature.find(":")
    msep = method_signature.rfind('.', 0, ci)
    if msep == -1:
        raise Exception("Unknown seperator in method signature %s" % method_signature)
    return method_signature[0:msep], method_signature[msep+1:]

# seperates classname from methodname while killing arguments (for parsing
# source code, not class file)
def splitcall(method_signature):
    data = method_signature.split(":")
    if len(data) != 2:
        raise Exception("Unknown method signature %s" % method_signature)
    cm, args = data
    msep = cm.rfind('.')
    if msep == -1:
        raise Exception("Unknown seperator in method signature %s" % method_signature)
    return cm[0:msep], cm[msep+1:]

def check_in(javad_path, target_method):
    method_name = extract_name(target_method)
    for line in open(javad_path):
        if line.find(method_name) != -1:
            return True

def find_signature(javad_path, target_classname, target_method):
    #print "Searching %s for %s.%s" % (javad_path, target_classname, target_method)

    if not check_in(javad_path, target_method):
        return

    parser = JavadParser()
    parser.parse_path(javad_path)

    for method in parser.get_methods():
        for invokation in method.invokations:
            if invokation.method == target_method:
                #print invokation
                if invokation.type in ['virtual', 'interface']:
                    acceptable_classnames = [invokation.classname] + getsubclasses(invokation.classname)
                else:
                    acceptable_classnames = [invokation.classname]

                #print acceptable_classnames
                if target_classname in acceptable_classnames:
                    package = parser.classdef.package
                    sourcefilename, sourcelineno = find_lineno(method.signature, invokation.index)
                    print '%s:%s:%d' % (package.replace('.', '/'), sourcefilename, sourcelineno)

# This program assumes that 
# * All java files have compiled successfully
# * All class files have been parsed with javad and stored in /tmp/jcall
if __name__ == '__main__':
    build_path = sys.argv[1] # where class files live
    target_method_signature = sys.argv[2] # something like my.Student.setName(Ljava.lang.String;)V
    #print target_method_signature

    target_classname, target_method = splitinvoke(target_method_signature)

    db = dbm.open('/tmp/jcall'+build_path+'/linenos', 'c')
    classsig = dbm.open('/tmp/jcall'+build_path+'/classsig', 'c')

    #print "Searching for %s %s in %s" % (target_classname, target_method, build_path)

    for root, dirs, files in os.walk('/tmp/jcall'+build_path):
        for name in files:
            if name.endswith('.javap'):
                find_signature(os.path.join(root, name), target_classname, target_method)
