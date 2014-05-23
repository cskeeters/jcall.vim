import os
import sys
import re
import shelve
from jcall import JavadParser
from filelock import FileLock

if __name__ == "__main__":

    build_path = sys.argv[1] # where class files live
    javad_path = sys.argv[2]
    tmp_path = sys.argv[3] # where class files live

    with FileLock(tmp_path+build_path+'/parsed.lock'):
        parsed = shelve.open(tmp_path+build_path+'/parsed', 'c')
        try:
            parser = JavadParser()
            parser.parse_path(javad_path)
            classdef = parser.get_classdef()
            #shelve
            parsed[classdef.name] = parser

        except Exception:
            print "Error parsing javap file %s" % name
        finally:
            parsed.close()
