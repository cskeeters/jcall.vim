import os
import sys
import re
import shelve
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

class JavadError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return self.value

def extract_name(method_signature):
    pre, args = method_signature.split(":")
    return pre.split(".")[-1]

# returns (type, object) for parsed line
class JavadParser:
    def __init__(self):
        self.parsing_path = ""
        self.source = None
        self.classdef = None
        self.methods = []

    def get_classdef(self):
        return self.classdef

    def get_source(self):
        return self.source

    def get_methods(self):
        return self.methods

    def sanity_check(self):
        if self.source == None:
            raise JavadError("Did not parse source file.  Was '-g' passed to javac at the time of compile?")

    def parse_handle(self, file):
        lineno=1
        for line in file:
            self.parse_line(line, lineno)
            lineno+=1
        self.sanity_check()

    def parse_path(self, path):
        self.parsing_path = path # for errors
        file = open(path)
        try:
            self.parse_handle(file)
        except JavadError, e:
            raise JavadError("Error parsing %s: %s" % (path, e.value))
        file.close()
        self.sanity_check()


    def parse_line(self, line, lineno=0):
        m=source_pattern.match(line)
        if m != None:
            self.source = m.group(1)

        m=class_pattern.match(line)
        if m != None:
            self.classdef = dotdict()
            self.classdef.access = m.group(1)
            self.classdef.abstract = m.group(2)
            self.classdef.final = m.group(3)
            self.classdef.type = m.group(4)
            self.classdef.name = m.group(5)
            package_sep_index = self.classdef.name.rfind('.')
            if package_sep_index != -1:
                self.classdef.package = self.classdef.name[0:package_sep_index]
            else:
                self.classdef.package = ''
            self.classdef.extends = m.group(7)
            implements = m.group(9)
            if implements == None:
                self.classdef.implements = []
            else:
                self.classdef.implements = implements.split(",")
            #print "name:", self.classdef.name
            #print "Extends:", self.classdef.extends
            #print "Implements:", self.classdef.implements

        m=static_pattern.match(line)
        if m != None:
            method = dotdict()
            method.name = 'static'
            method.signature = '%s.static' % (classname)
            method.invokations = []
            self.methods.append(method)

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
            method.signature = "%s.%s:(%s)V" % (self.classdef.name, method.name, arguments) # const always shows void return
            method.invokations = []

            self.methods.append(method)

        else: #test for method only if not a constructor

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
                method.signature = "%s.%s:(%s)%s" % (self.classdef.name, method.name, arguments, argtrans(method.return_type))
                method.invokations = []

                self.methods.append(method)

        m=invoke_pattern.match(line)
        if m != None:
            invokation = dotdict()
            invokation.index = int(m.group(1))
            invokation.type = m.group(2)
            invokation.method_signature = m.group(3) # what I'm calling

            if invokation.method_signature.find(".") == -1:
                invokation.classname = self.classdef.name
                invokation.method = invokation.method_signature
                invokation.method_signature = "%s.%s" % (invokation.classname,invokation.method)
            else:
                invokation.method_signature = invokation.method_signature.replace('/', '.')
                invokation.classname, invokation.method = splitinvoke(invokation.method_signature)

            invokation.name = extract_name(invokation.method_signature)

            if len(self.methods) == 0:
                raise JavadError("Invocation without method definition")

            self.methods[-1].invokations.append(invokation)

        m=lineno_pattern.match(line)
        if m != None:
            if len(self.methods) == 0:
                raise JavadError("%s Matched lineno_pattern without method in %s" % (line, self.source))

            method = self.methods[-1]

            if not method.has_key('linerefs'):
                method.linerefs = []

            lineref = dotdict()
            lineref.lineno=int(m.group(1))
            lineref.index=int(m.group(2))
            method.linerefs.append(lineref)
            #print '%s:%s -> %s:%s' % (method, m.group(2), sourcefile, m.group(1))

# Translates 'byte' into 'B' and 'java/lang/Object[]' into 'Ljava.lang.object[;'
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
        type = type.replace('.', '/')
        if m.group(2) == '[]':
            type+='['
        return type+";"
    raise Exception("could not translate argument "+a)

class JTree:
    def __init__(self, tmp_path, build_path):
        # Not all decedents, just children
        self.child_classes = {}
        self.implementing_classes = {}
        self.parsed = shelve.open(tmp_path+build_path+'/parsed')
        self.init_trees()

    def __del__(self):
        self.parsed.close()

    def get_parsers(self):
        for key in self.parsed.keys():
            yield self.parsed[key]

    def init_trees(self):
        for classname in self.parsed.keys():
            parser = self.parsed[classname]

            if not self.child_classes.has_key(parser.classdef.extends):
                self.child_classes[parser.classdef.extends] = [classname]
            else:
                self.child_classes[parser.classdef.extends] += [classname]

        for classname in self.parsed.keys():
            parser = self.parsed[classname]

            for impl in parser.classdef.implements:
                if not self.implementing_classes.has_key(impl):
                    self.implementing_classes[impl] = [classname] + self.get_desc_classes(classname)
                else:
                    self.implementing_classes[impl] += [classname] + self.get_desc_classes(classname)

    def get_desc_classes(self, classname):
        try:
            desc = []
            for child in self.child_classes[classname]:
                desc += [child] + self.get_desc_classes(child)
            return desc
        except KeyError, e:
            # Hard to know if this is a system level class or the db is corrupt
            return []

    def get_implementing_classes(self, interfacename):
        try:
            return self.implementing_classes[interfacename]
        except KeyError, e:
            return []


    # Lower defined as further away from Object in the class hierarchy
    def get_lowest(self, classname, method_signature):
        found = False
        try:
            parser = self.parsed[classname]
            #print "checking", parser.classdef.name, "which extends", parser.classdef.extends
            for method in parser.get_methods():
                c, m = splitinvoke(method.signature)
                #print m, method_signature
                if m == method_signature:
                    return classname

            if not found:
                return self.get_lowest(parser.classdef.extends, method_signature)

        except KeyError, e:
            pass # We're probably not looking for invokations of Object methods
            #print "Error getting parser for "+classname+".  "
            #raise Exception("Error getting parser for "+classname+".  ")

        return None

    def get_ii(self, interfacename, method_signature):
        defining_interface = self.get_lowest(interfacename, method_signature)
        if None != defining_interface:
            interfaces = [defining_interface] + self.get_desc_classes(defining_interface)
            #then find all classes that implement any of those interfaces
            potential_classes = set()
            for interface in interfaces:
                classes = self.get_implementing_classes(interface)
                for c in classes:
                    potential_classes.add(self.get_lowest(c, method_signature))
            return interfaces + list(potential_classes)
        return []

    def get_acceptable_classnames(self, invokation):
        acceptable_classnames = [invokation.classname]
        if invokation.type  == 'virtual':
            acceptable_classnames = [jtree.get_lowest(invokation.classname, target_method)] + jtree.get_desc_classes(invokation.classname)
        if invokation.type == 'interface':
            acceptable_classnames = jtree.get_ii(invokation.classname, target_method)
        return acceptable_classnames

    def get_index_list(self, method_signature):
        classname, method = splitinvoke(method_signature)
        parser = self.parsed[classname]
        for method in parser.get_methods():
            if method.signature == method_signature:
                return parser.source, method.linerefs
        raise Exception("Could not find linerefs for %s" % method_signature)

    # Returns Main.java:34 for (my.Main.main:(I[C)V, 0)
    def find_lineno(self, method_signature, index):
        #print "Finding %s:%s" % (method, index)
        try:
            source, index_list = self.get_index_list(method_signature)
            curindex = -1
            curlineno = None
            for record in index_list:
                i = record['index']
                lineno = record['lineno']
                #print i, source
                if i <= index:
                    if i > curindex:
                        curindex = i;
                        curlineno = lineno
            return (source, curlineno)
        except KeyError:
            raise Exception("Error finding linenos for %s" % method)

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

# This program assumes that
# * All java files have compiled successfully
# * All class files have been parsed with javad and stored in g:jcall_tmp_path (/tmp/jcall)
if __name__ == '__main__':
    build_path = sys.argv[1] # where class files live
    target_method_signature = sys.argv[2] # something like my.Student.setName(Ljava.lang.String;)V
    tmp_path = sys.argv[3] # where class files live
    #print target_method_signature

    target_classname, target_method = splitinvoke(target_method_signature)

    jtree = JTree(tmp_path, build_path)
    #print "Searching for %s %s in %s" % (target_classname, target_method, build_path)

    for parser in jtree.get_parsers():
        for method in parser.get_methods():
            for invokation in method.invokations:
                if invokation.method == target_method:
                    #print "Method %s.%s, %s" % (invokation.classname, invokation.method, invokation.type)

                    acceptable_classnames = jtree.get_acceptable_classnames(invokation)

                    #print target_classname, acceptable_classnames
                    if target_classname in acceptable_classnames:
                        package = parser.classdef.package
                        sourcefilename, sourcelineno = jtree.find_lineno(method.signature, invokation.index)
                        if sourcefilename != None:
                            print '%s:%s:%d' % (package.replace('.', '/'), sourcefilename, sourcelineno)
