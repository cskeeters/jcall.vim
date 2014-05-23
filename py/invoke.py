import sys
import os
import re
import shelve
from jcall import argtrans
from jcall import splitinvoke
from jcall import JavadParser
from jcall import check_in
from jcall import JTree

def getoutput(cmd):
    pipe = os.popen(cmd, 'r', 4096)
    output = pipe.read().strip()
    pipe.close()
    return output

def find_signature(parser, acceptable_classnames, invokation):
    target_classname, target_method = splitinvoke(invokation.method_signature)

    if parser.classdef.name in acceptable_classnames:
        for method in parser.get_methods():
            cur_specific_signature = splitinvoke(method.signature)[1]
            #print cur_specific_signature, target_method
            if cur_specific_signature == target_method:
                package = parser.classdef.package.replace('.', '/')
                try:
                    if len(method.linerefs) > 0:
                        print '%s:%s:%d' % (package, parser.source, method.linerefs[0].lineno-1)
                except AttributeError, e:
                    #print "Method %s has no line reference information, it may be abstract (or an interface)" % method.signature
                    #sys.exit(100)
                    print '%s:%s:%d' % (package, parser.source, 1)


def search_for(jtree, invokation):
    acceptable_classnames = [invokation.classname]
    if invokation.type  == 'virtual':
        acceptable_classnames = [jtree.get_lowest(invokation.classname, invokation.method)] + jtree.get_desc_classes(invokation.classname)
    if invokation.type == 'interface':
        acceptable_classnames += jtree.get_ii(invokation.classname, invokation.method)

    for parser in jtree.get_parsers():
        find_signature(parser, acceptable_classnames, invokation)

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

def print_invokes(jtree, parser, target_lineno, target_name):
    for method in parser.get_methods():
        if method.has_key('linerefs'):
            for lineref in method.linerefs:
                if lineref.lineno == target_lineno:
                    #print "match line number at ", parser.source, lineref.lineno, lineref.index
                    invokation = get_next_invoke(method, lineref.index, target_name)
                    search_for(jtree, invokation)

def get_parsers(jtree, filename):
    parsers = []
    for parser in jtree.get_parsers():
        if parser.source == filename:
            parsers.append(parser)
    return parsers

if __name__ == "__main__":

    filepath = sys.argv[1]
    lineno = int(sys.argv[2])
    target_name = sys.argv[3]
    build_path = os.path.normpath(sys.argv[4])
    tmp_path = os.path.normpath(sys.argv[5])

    filename = os.path.basename(filepath)
    jtree = JTree(tmp_path, build_path)

    for parser in get_parsers(jtree, filename):
        print_invokes(jtree, parser, lineno, target_name)
