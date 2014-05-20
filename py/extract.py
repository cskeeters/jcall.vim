import os
import sys
import re
import dbm
import marshal
from jcall import JavadParser

def write_subclasses(build_path, subclasses):
    classsig = dbm.open('/tmp/jcall/'+build_path+'/classsig', 'c')

    for classname, subclasses in subclasses.iteritems():
        classsig[classname] = marshal.dumps(list(set(subclasses)))

def write_linenos(build_path, linerecords):
    db = dbm.open('/tmp/jcall/'+build_path+'/linenos', 'c')
    for method_signature, index_list in linerecords.iteritems():
        db[method_signature] = marshal.dumps(index_list)

def get_sub_classes(classname, extends, implements):
    subclasses = []
    for sub, super in extends.iteritems():
        if super == classname:
            #print "%s extends %s" % (sub, super)
            subclasses.append(sub)
            subclasses += get_sub_classes(sub, extends, implements)

    for c, il in implements.iteritems():
        for impl in il:
            if impl == classname:
                #print "%s implements %s" % (c, impl)
                subclasses.append(c)
                subclasses += get_sub_classes(c, extends, implements)

    return subclasses

if __name__ == "__main__":

    build_path = sys.argv[1] # where class files live

    subclasses = {}
    linerecords = {}

    classnames = []
    extends = {}
    implements = {}

    for root, dirs, files in os.walk('/tmp/jcall'+build_path):
        for name in files:
            if name.endswith('.javap'):
                try:
                    javad_path = os.path.join(root, name)
                    parser = JavadParser()
                    parser.parse_path(javad_path)
                    classdef = parser.get_classdef()

                    classnames.append(classdef.name)

                    if classdef.extends != None:
                        extends[classdef.name] = classdef.extends
                    implements[classdef.name] = classdef.implements

                    for method in parser.get_methods():
                        if method.has_key('linerefs'):
                            for lineref in method.linerefs:

                                #sourcepath = classname.replace('.', '/')+".java"
                                t = (lineref.index, parser.source, lineref.lineno)

                                if not linerecords.has_key(method.signature):
                                    linerecords[method.signature] = [t]
                                else:
                                    linerecords[method.signature].append(t)
                except Exception:
                    print "Error parsing javap file %s" % name

    for classname in classnames:
        #print "Looking for classname", classname
        subs = get_sub_classes(classname, extends, implements)
        #print classname, subs
        subclasses[classname] = list(set(subs))

    write_subclasses(build_path, subclasses)
    write_linenos(build_path, linerecords)
