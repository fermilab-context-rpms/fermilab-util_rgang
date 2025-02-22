#!/bin/env python3
#   This file (rgang.py) was created by Ron Rechenmacher <ron@fnal.gov> on
#   Apr 13, 2001. "TERMS AND CONDITIONS" governing this file are in the README
#   or COPYING file. If you do not have such a file, one can be obtained by
#   contacting Ron or Fermi Lab in Batavia IL, 60510, phone: 630-840-3000.
#   $RCSfile: rgang.py,v $ $Revision: 1.213 $ $Date: 2025/01/14 21:52:08 $

rcs_keyword='$Revision: 1.213 $$Date: 2025/01/14 21:52:08 $'
VERSION='3.9.4 cvs: %s'%(rcs_keyword,)

import os.path                          # basename
import sys                              # argv
import re                               # findall
import time                             # time
import signal                           # signal
import errno                            # EINTR, EAGAIN
import traceback                        # format_exception
import pickle                           # dumps
import pprint                           # pprint
import math                             # ceil
import select                           # select
import zlib                             # crc32

PY3_ = sys.version_info[0] >= 3    # python 3+

DFLT_RSH='ssh'
DFLT_RCP='scp'
DFLT_RSHTO='150.0'                      # float seconds  (basically, let the user decide)
DFLT_RCPTO='3600.0'                     # float seconds (big files?) (basically, let the user decide)
DFLT_SH='/bin/bash'

def where(ff):
    ff='/'+ff
    for pp in os.environ['PATH'].split(':'):
        if os.access(pp+ff,os.X_OK): return pp
        pass
    return ''
dd=os.path.dirname(sys.argv[0])
if dd == '': dd = where(sys.argv[0])
#DFLT_PATH=os.path.abspath(dd) # when pwd=/home... and bin/rgang, will produce
                               #  /mnt/disk1/home/... instead of just /home/...
DFLT_PATH=os.popen('cd %s;pwd'%(dd,)).readlines()[0][:-1]

APP = os.path.basename( sys.argv[0] )
USAGE=\
"%s: run cmds on hosts\n"%(APP,)+\
"Usage: %s [options] <nodespec> [cmd]\n"%(APP,)+\
"       %s [options] -<c|C> <nodespec> 'srcfile' 'dstdfile'\n"%(APP,)+\
"       %s [--skip <nodespec>] --list [<nodespec>]\n"%(APP,)+\
"       %s -d\n"%(APP,)
USAGE_V=\
"\n<nodespec> can be a \"farmlet\", \"expandable node list\", or \"-\".\n"+\
"  when nodespec is \"-\", nodes are read from stdin (1 per line)\n"+\
"  until a line containing a single \".\" is encountered\n"+\
"  The nodespec is evaluated in the following order:\n"+\
"      is it the stdin (\"-\")\n"+\
"      it it a file in \"farmlets\" directory\n"+\
"      it it a file in current working directory\n"+\
"      assume \"expandable node list\"\n"+\
"Examples: %s -c root@qcd01{01-4} .profile .\n"%(APP,)+\
"          %s all ls\n"%(APP,)+\
"          %s all \"echo 'hi  there'\"\n"%(APP,)+\
"          %s qcd0101,qcd0104 '%s qcd01{01-4} \"echo hi\"'\n"%(APP,APP)+\
"          %s qcd01{01-4} '%s qcd01{01-4} \"echo hi\"'\n"%(APP,APP)+\
"          %s -l root qcd0{1-2}{04-10} \"echo 'hi  there'\"\n"%(APP,)+\
"          %s --skip node1{b-d} --list \"node{04-0x44,4f-0x55}\"\n"%(APP,)+\
" to test a large # of nodes:\n"+\
"          %s 'qcd{,,,}{01-8}{01-10}' echo hi\n"%(APP,)+\
"Node spec. can be a single node, a comma separated list, or contain an\n\
       expansion spec.\n\
Node spec. Expansion: expansion occurs within braces ({}). Three groups of\n\
       expansion can be specified:\n\
       1) comma list expansion: node{a,2,c} becomes: nodea node2 nodec.\n\
       2) alpa range: node{a-c} becomes: nodea nodeb nodec.\n\
       3) numeric range (dec,hex,octal, all with optional 0 fill):\n\
          (Zero fill is specified on the first number, base on the 2nd)\n\
          node{08-11} becomes: node08 node09 node10 node11\n\
          node{9-0xb} becomes: node9 nodea nodeb\n\
          node{6-010} becomes: node6 node7 node10\n\
       Range expansion can occur in a list:\n\
          node{6,9-11} becomes: node6 node9 node10 node11\n\
       Multiple expansions can be specified:\n\
          node{6,9}{a,b} becomes: node6a node6b node9a node9b\n\
          node{6,9-10}{,a} becomes: node6 node6a node9 node9a node10 node10a\n\
       Comma list and expansion can be used together:\n\
          nodez,node{a-c} becomes: nodez nodea nodeb nodec\n\
Note: when using node expansion, don't forget to quote (or escape) the\n\
       expression to stop shell expansion (as bash would do with the \"{,}\"\n\
       syntax in above examples). Example: node\\{6,9-10} OR 'node{6,9-10}{,a}'\n\
--serial note: If --serial is used with 2000 nodes and the default --nway=200,\n\
      the result would be 200 groups of 10_nodes_in_parallel (2000/200=10).\n\
      Setting --nway=1 with 2000 nodes would cause rgang to attempt 1 group\n\
      of 2000 nodes (2000/1=2000) which would cause rgang to fail (most likely)\n\
      because of excessive resource (sockets) use. If --nway=0, then rgang\n\
      internally resets nway to the number of nodes (2000 in this example).\n\
      With less than (the default nway) 200 nodes, --serial, will result in\n\
      basic \"serial\" (one node at a time) operation.  The --serial=val does the\n\
      --nway option automatically but is more intuitive; it is the number of\n\
      nodes that will be processed in parallel (as a group). --serial=1 results\n\
      in serial operation for any number of nodes.\n\
env.vars set by rgang:\n\
      RGANG_MACH_ID, RGANG_INITIATOR, RGANG_PARENT, RGANG_PARENT_ID, RGANG_NODES\n\
rgang sources $HOME/.rgangrc\n\
Sending SIGQUIT (usually ctl-\\) to the main rgang process should print out\n\
the following status line (possibly overwriting some existing output):\n\
\\rnodes=     stOB=       stEB=       inc=     ok=     err=     conn=    expt=   \n\
With:\n\
  nodes= with the # of nodes\n\
  stOB=  with the # of standard output characters buffer\n\
  stEB=  with the # of standard error characters buffer\n\
  inc=   with the # of nodes which are in the incomplete state\n\
  ok=    with the # of nodes which have completed with an OK status\n\
  err=   with the # of nodes which have completed with an error status\n\
  conn=  with the # of \"connections\"\n\
  expt=  with the # of expected connections (depends on nways/serial values)\n\
Sending SIGINT (ctl-C), to kill rgang, will give the user 3 seconds to stop all\n\
remaining output. After 3 seconds, all buffered output is printed.\
"
# For the following, the definitions are:
#       'desc'   Short description; printed out along with "USAGE"
#       'init'   The initialized value, i.e. when option is not specified;
#                usually string, but can be other if accompanied by specific
#                processing (default='')
#       'alias'  a list of aliases (i.e. short form?)
#       'arg'    the type of option argument:
#                an integer 
#                  0 => option does not take an argument (default)
#                  1 => option does take an argument
#                  2 => option takes an optional argument where if it is
#                       multiple letter (long [--] form) option there must
#                       be an '=<value>', else if it is a single letter,
#                       the arg will follow 
#       'opt'    for optional argument type options (arg=2), the
#                value of the option when specified without an argument
OPTSPEC={ 'd':{'desc':"List farmlet names"},
          's':{'desc':"Skip current (local) node"},
          'c':{'desc':"Copy input output"},
          'C':{'desc':"Copy and skip current (local) node. Equiv to -sc"},
          'p':{'desc':"Same as rcp -p (only applicable if -c/C)"},
          'x':{'desc':"Same as rsh/rcp -x (turns on encryption)"},
          'X':{'desc':"Same as rsh/rcp -X (turns off encryption)"},
          'f':{'desc':"Same as rsh -f (forward nonforwardable credentials)"},
          'F':{'desc':"Same as rsh/rcp -F (forward forwardable credentials)"},
          'N':{'desc':"Same as rsh/rcp -N (prevent credential forwarding)"},

          # This block of options has arg or optional arg
          'l':{'desc':"Same as rsh -l (only applicable if not -c/C)",'arg':1},
          'n':{'desc':"-n or -n0: no header, -n1 or -nn: node=, -n2: ---,\n\
                       -n3: --- and cmd", 'arg':2,'init':'','opt':'0'},
          'farmlets':{'desc':"override farmlets dir /usr/local/etc/farmlets",
                      'arg':1,'init':'/usr/local/etc/farmlets'},
          'serial'  :{'desc':"do not fork all commands before reading output (works\n\
                       with nway)", 'arg':2,'init':'','opt':'0'},
          'skip'    :{'desc':'skip this specific list of nodes','arg':1},
          'rsh'     :{'desc':'override default rsh (use quotes to include options) default=%s'%(DFLT_RSH),'arg':1,'init':DFLT_RSH},
          'rcp'     :{'desc':'override default rcp','arg':1,'init':DFLT_RCP},
          'sh'      :{'desc':'override default sh (use quotes to include options) default=%s'%(DFLT_SH),'arg':1,'init':DFLT_SH},
          'nway'    :{'desc':'number of branches for each node of the tree OR if\n\
                       --serial, # of groups (def=200)', 'arg':1,'init':200},
          'tlvlmsk' :{'desc':"debugging; set hex debug mask i.e. 0xf, \"1<<9\"",'arg':2,'opt':1,'init':'0'},
          'rshto'   :{'desc':"change non-copy default timeout val %s (float seconds)"%DFLT_RSHTO,
                      'arg':1,'init':DFLT_RSHTO},
          'rcpto'   :{'desc':"change the default timeout value %s (float seconds)\n\
                       for the copy"%DFLT_RCPTO, 'arg':1,'init':DFLT_RCPTO},
          'err-file':{'desc':"file to write timedout/error nodes to (could be used for\n\
                       retry)", 'arg':1 },
          'pypickle':{'desc':"implies pyret but *final* result is pickled and printed\n\
                       (preceeded by 8 length chars) 0=just final,1=intermediate",
                      'arg':2,'opt':'1'},
          'path'    :{'desc':"prepend to path when rsh rgang (i.e. nodes>nway)\n\
                       (dflt:%s)"%(DFLT_PATH,),'arg':1,'init':DFLT_PATH},
                             # check out: rgang --path=/tmp --nway=1 'fnapcf.fnal.gov{,,}' 'printenv PATH'
          'app'     :{'desc':"change application name from default \"%s\" (use when\n\
                       call from script)"%(APP,),'arg':1,'init':APP},
          'mach_idx_offset' :{'desc':"INTERNAL - used to determine \"root\" machine",'arg':1},

          'list'    :{'desc':"list farmlets (their contents)"},
          'ditto'   :{'desc':'Attempt to detect when output is same as previous (using\n\
                       crc32) and print "ditto"'},
          'combine' :{'desc':"spawn commands with stderr dupped onto stdout"},
          'do-local':{'desc':"INTERNAL option - tells rgang to do 1st node in current\n\
                       (local) environment; do not rsh"},
          'pty'     :{'desc':"use pseudo term -- good for when ssh wants passwd"},
          'verbose' :{'desc':"verbose (including a bit more with -h)",'alias':['v']},
          'pyret'   :{'desc':"don't output to stdout/err (used when rgang is imported\n\
                       in other .py scripts)"},
          'pyprint' :{'desc':"implies pyret but *final* result is printed (this option\n\
                       negated by pypickle)"},
          'input-to-all-branches' :{'desc':"send input to all branches, not just currently\n\
                          processed"},
          'adjust-copy-args':{'desc':"INTERNAL - applicable for \"-c\" (copy-mode)"},
          }


def getopts( optspec, argv, usage_in, usage_v_in, app, version='' ):
    import os                           # environ
    import string                       # replace, split
    import sys                          # exit
    import re                           # sub
    optspec.update({'help'   :{'alias':['h','?'],
                               'desc':'print usage/help. A bit more with -v'}})
    optspec.update({'version':{'alias':['V'],'desc':'print cvs version/date'}})
    opt_map={}                          # handles aliases
    opt={}                              # local master options dictionary
    long_opts = []; env_opts = []
    env_app=re.sub( r'\..*', '', re.sub('-','_',app).upper() )
    # look for options from environment first as they may be overridden
    # by command line options
    if env_app+'_OPTS' in os.environ.keys():
        argv = os.environ[env_app+'_OPTS'].split() + argv
    for op in optspec.keys():
        default = {'desc':'', 'init':'', 'alias':[], 'arg':0, 'opt':''}
        default.update( optspec[op] ); optspec[op].update( default )
        opt_map[op] = op; dashes='-'
        if len(op) > 1: long_opts.append(op); dashes='--'
        for alias in optspec[op]['alias']:
            opt_map[alias] = op
            if len(alias) > 1: long_opts.append(alias)
        env=env_app+'_'+op.replace('-','_')
        env=env.upper()
        if env in os.environ.keys():
            if optspec[op]['arg']:
                  ee=os.environ[env]
                  opt[op]=ee;  env_opts.append(dashes+op+'='+ee)
            else: opt[op]='1'; env_opts.append(dashes+op)
        else:     opt[op]=optspec[op]['init']
    # add to usage
    usage_out = "\n\
Note: all options can be specified via environment variables of the form\n\
      %s_<OPTION> where option is all uppercase\n\
      OR in a single %s_OPTS env.var.\n\
Options:\n"%(env_app,env_app)
    if PY3_: xx=sorted(optspec.keys())
    else:    xx=optspec.keys(); xx.sort()   # the python 2 way
    for op in xx:
        dash=''
        for op_ in [op]+optspec[op]['alias']:
            if len(op_) == 1: dash=dash+',-'+op_
            else:             dash=dash+',--'+op_
            if len(op_) == 1 and optspec[op]['arg'] == 1: dash=dash+'<val>'
            elif                 optspec[op]['arg'] == 1: dash=dash+'<=val>' 
            if len(op_) == 1 and optspec[op]['arg'] == 2: dash=dash+'[val]'
            elif                 optspec[op]['arg'] == 2: dash=dash+'[=val]' 
        usage_out = usage_out + '  %-20s %s\n'%(dash[1:],optspec[op]['desc'])
    # --- done with usage additions
    long_space_separated = ' '+' '.join(long_opts)
    opts=[] # to remember all args passwd
    while argv and argv[0][0] == '-' and len(argv[0]) > 1:
        op = argv[0][1:]; opts.append(argv.pop(0))      # save all opts
        long_flg = 0    # SHORT FORM is default
        if op[0] == '-':
            long_flg = 1    # LONG FORM
            op = op[1:]
            # check for '=' and prepare possible op_arg. (adding the '=' is a
            op=op+'='
            op,op_arg = op.split( '=', 1 ) #trick, it gets removed)
            op_grp = [op]
        else: op_grp = [ xx for xx in op ] # convert string to list
        while op_grp:
            op_ = op_grp.pop(0)
            if long_flg and not op_ in long_opts:
                possibles = re.findall(" "+op_+"[^ ]*",long_space_separated)
                if   len(possibles) == 1: op_ = possibles[0][1:]
                elif len(possibles) > 1:
                    pp = ''.join(possibles)
                    sys.stderr.write('ambiguous "long" option: %s\ncould be:%s\n'%(op_,pp))
                    sys.exit(1)
                else: sys.stderr.write('%s: unknown "long" option: %s\n'%(APP,op_)); sys.exit(1)
            elif not long_flg and not op_ in opt_map.keys():#OK, no short list.
                sys.stderr.write('unknown option: %s\n'%(op_,)); sys.exit(1)
            op_ = opt_map[op_] # unalias
            if   optspec[op_]['arg'] == 0: ### NO OPTION ARG
                if long_flg and op_arg:
                    sys.stderr.write('option %s does not take an argument\n'%(op_,))
                    sys.exit(1)
                if not opt[op_]: opt[op_] = '1'
                else:            opt[op_] = str(int(opt[op_]) + 1)
            elif optspec[op_]['arg'] == 1: ### OPTION ARG
                if long_flg and op_arg:
                    opt[op_] = op_arg[:-1] # strip off added '='
                elif not long_flg and op_grp:
                    opt[op_] = ''.join(op_grp); op_grp = []
                elif not argv:
                    sys.stderr.write('option %s requires and argument\n'%(op_,)); sys.exit(1)
                else: opt[op_]=argv[0]; opts.append(argv.pop(0))# save all opts
            elif long_flg and op_arg:            ### OPTIONAL OPTION ARG
                opt[op_] = op_arg[:-1] # strip off added '='
            elif not long_flg and op_grp:
                opt[op_] = ''.join(op_grp); op_grp = []
            else: opt[op_] = optspec[op_]['opt']
    if opt['version']:
        if version == '':
            try: version = VERSION  # incase VERSION is not set (this is generic code) -
            except: TRACE( 10, 'except - version' )  # version will just remain ''
        sys.stdout.write( 'Rgang version: %s\n'%(version,) )
        sys.stdout.write( "Python version: %s on %s\n"%(sys.version,sys.platform) )
        sys.exit( 0 )
    if opt['help']:
        if opt['verbose']: sys.stdout.write( usage_in+usage_out+usage_v_in+'\n' ); sys.exit( 0 )
        else:              sys.stdout.write( usage_in+usage_out+'\n' );            sys.exit( 0 )
    return env_opts+opts,argv,opt,usage_out
    #getopts


# this needs g_opt['tlvlmsk']
# standard TRACE usage:
#   grep 'TRACE( *[0-9]*,' rgang.py | sed 's/.*TRACE(/TRACE(/' | sort -k2n
#   grep 'TRACE( *[0-9]*,' rgang.py | sed 's/.*TRACE( *//;s/,.*//' | sort -nu
# lvl                         lvl
#  0 try_line                  16 rmt_sh_sts
#  1                           17 alphanum_range_expand
#  2 info_clear,...            18 expand
#  3 g_opt                     19 expand
#  4 args                      20 child close
#  5 local spawn_cmd           21 spawn_cmd
#  6 initial spawn_cmd         22 spawn_cmd
#  7 get_output                23 spawn_cmd, get_nway_indexes
#  8 chk_exit, stdin           24 try_line
#  9 branch_input_l            25 try_line
# 10 exceptions                26 get_output
# 11 PICKLE                    27 get_output
# 12 rmt_sh_sts                28 initiator_node_status
# 13 spawn_cmd                 29 get_output
# 14 spawn_cmd                 30 main KeyboardInterrupt
# 15 spawn_cmd                 31 get_output, timeout_*
#import sys;g_opt={'tlvlmsk':0xffffffff};g_thisnode=None
if sys.version_info[0] == 2: exec( 'trc_one=1L' )
else:                        exec( 'trc_one=1' )

def TRACE( lvl, fmt_s, *args ):
    import socket,time,os
    global g_thisnode
    # how is g_opt working w/o "global" declaration? - must default if read
    if g_opt['tlvlmsk'] & (trc_one<<lvl):
        if g_thisnode == None: g_thisnode=NodeInfo()
        msg='%.3f:%s:%s:%d:%s\n'%(time.time(),socket.gethostname(),
                                  g_thisnode.mach_idx,lvl,fmt_s%args)
        fo = open( "%s.%s.trc"%(g_thisnode.hostnames_l[0],os.getenv('RGANG_MACH_ID')), "a+" )
        fo.write( msg )
        #fd = fo.fileno()
        #os.write( fd,msg )
        fo.close()
    # TRACE


class NodeInfo:
    def __init__( self ):
        import socket                       # gethostname()
        import os
        nn = socket.gethostname()
        try: xx = socket.gethostbyaddr( nn )
        except: xx = (nn,[nn],[])
        self.hostnames_l = [xx[0]]
        self.alias_l     = xx[1]
        self.ip_l        = xx[2]
        ss = xx[0].split(".")
        if len(ss) == 1: self.shortnames_l = self.hostnames_l
        else:            self.shortnames_l = [ss[0]]
        try: # must "try" because this aint going to work under every os
            # get a list of inet address for all interfaces and aliases
            os_fo = os.popen( "/sbin/ifconfig 2>/dev/null | grep 'inet ' | sed -e 's/.*inet //' -e 's/addr://' -e 's/ .*//'" )
            ll = os_fo.readlines()
            if g_opt['verbose'] and int(g_opt['verbose']) >= 2: sys.stderr.write('NodeInfo __init__ ifconfig returned %d lines\n'%(len(ll),))
            for inet_addr in ll:
                xx = socket.gethostbyaddr(inet_addr[:-1])
                self.hostnames_l = self.hostnames_l + [xx[0]]
                self.alias_l     = self.alias_l     + xx[1]
                self.ip_l        = self.ip_l        + xx[2]
                ss = xx[0].split(".")
                if len(ss) == 1: self.shortnames_l = self.shortnames_l + ss
                else:            self.shortnames_l = self.shortnames_l + [ss[0]]
                if g_opt['verbose'] and int(g_opt['verbose']) >= 2: sys.stderr.write('NodeInfo __init__ shortnames_l=%s alias_l=%s\n'%(self.shortnames_l, self.alias_l))
            os_fo.close()
        except:
            exc, value, tb = sys.exc_info()
            if g_opt['verbose'] and int(g_opt['verbose']) >= 2: sys.stderr.write('NodeInfo __init__ ifconfig EXCEPTION: %s: %s\n'%(exc,value))
            pass # no TRACE because TRACE may call this
        self.shortnames_l = self.shortnames_l + ['localhost']
        self.ip_l         = self.ip_l         + ['127.0.0.1']
        self.mach_idx = '?'  # rgang specific
    def is_me( self, node ):
        # NOTE: I feel that using gethostbyaddr, which potentially
        # contacts the names server, is not the right choice.
        if node.find(".") == -1:
            if    node in self.shortnames_l \
               or node in self.alias_l \
               or node in self.ip_l: return 1
            else:                    return 0
        else:
            if    node[:4] == '127.': return 1  # probably just a linux thing
            if    node in self.hostnames_l \
               or node in self.alias_l \
               or node in self.ip_l: return 1
            else:                    return 0
    # NodeInfo


# define a new general "Program Error"
class ProgramError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)
    pass


###############################################################################
# General Regular Expression class that allows for:
#    xx = Re( re )
#    ...
#    if xx.search( line ):
#        yy = xx.match_obj.group( x )
#

class Re:
    import re
    def __init__( self, reg_ex=None,flags=0 ):
        if reg_ex: self.compiled = self.re.compile(reg_ex,flags)
        self.match_obj=None
    def search(self,haystack):
        self.match_obj = self.compiled.search( haystack )
        return self.match_obj
    # Re

re_numeric = Re( r"^([0-9a-f]+)-((0x{0,1}){0,1}[0-9a-f]+)" )     # the "r" prefix --> use Python's raw string notation
re_1alpha  = Re( r"^([a-zA-Z])-([a-zA-Z])" )                     # the "r" prefix --> use Python's raw string notation

# the connect str will be the first thing that is *supposed to be* printed out.
CONNECT_MAGIC = "__rg_connect__"
re_connect  = Re( r"(.*)%s"%(CONNECT_MAGIC,) ) # the "r" prefix --> use Python's raw string notation

STATUS_MAGIC = "__rg_sts__:"  # Can I manipulate this so it is TRACE-able? --> note ("") appended in spawn_cmd
#re_status = Re( r"(.*)%s([0-9]+)$"%(STATUS_MAGIC,),re.MULTILINE ) # the "r" prefix --> use Python's raw string notation
# I'll assume that with the echo of the STATUS_MAGIC that ends with newline as
# defined in spawn_cmd, the re search does not need to be multiline (actually,
# I recall there may be a problem with MULTILINE
re_status  = Re( r"(.*)%s([0-9]+)"%(STATUS_MAGIC,) ) # the "r" prefix --> use Python's raw string notation

re_pickle = Re( r"PICKLE:([0-9a-f]{8}):$",re.M ); pickle_cookie_len = len('PICKLE:12345678:\n')
re_hex    = Re( r"^[0-9a-f]+" )

re_mach_id = Re( r"(.*[^\\]|^)\$(RGANG_MACH_ID|{RGANG_MACH_ID})([^a-zA-Z_].*|$)" ) # for rcp

re_mach = Re( r"^[^#\S]*([^#\s]+)" )


# If nested file feature is desired, should figure how to detect infinite loop.
def node_list_from_file( listfile ):
    if g_opt['verbose']: sys.stderr.write('reading list from file %s\n'%(listfile,))
    mach_l = []
    fo = open(listfile)
    TRACE( 2, "node_list_from_file fo.fileno()=%d", fo.fileno() )
    for xx in fo.readlines():
        if re_mach.search(xx):
            # remove any single or double quotes, which are illegal in hostnames and common
            # when a node list is exported to a csv file and "," is changed to nl
            mach_l.append(re_mach.match_obj.group(1).strip("\"'"))
    fo.close()
    return mach_l
#-node_list_from_file

def find_node_list_from_file( spec ):
    """\
    This will return a list of nodes (or "machines") OR [] if not a valid file.
    """
    mach_l = []
    if spec[0]=='/' or spec[:2]=='./':
        if os.path.isfile(spec) and os.access(spec,os.R_OK):
            listfile = spec
            mach_l = node_list_from_file( listfile )
            pass
        # error else where
        #else:
        #    sys.stderr.write('invaild farmlet path (not a file or not readable)\n')
        #    return []
    elif os.access(g_opt['farmlets']+'/'+spec,os.R_OK):    # you can always specify --farmlets=.
        listfile = g_opt['farmlets']+'/'+spec
        mach_l = node_list_from_file( listfile )
        pass
    return mach_l
#-find_node_list_from_file, node_list_from_file


def findall_expands( ss ):
    """\
    Returns a list of expand specs contained in ss. Example:
    with ss='this,that{1,2,{a-c}}{e-g}', return=['{1,2,{a-c}}', '{e-g}']
    """
    result = []; result_idx = 0; brace_lvl = 0
    for cc in ss:
        if   cc == '{':
            brace_lvl = brace_lvl + 1
            if brace_lvl == 1: result.append('')
        if brace_lvl > 0: result[result_idx] = result[result_idx] + cc
        if   cc == '}':
            brace_lvl = brace_lvl - 1
            if brace_lvl == 0: result_idx = result_idx + 1
    if brace_lvl != 0: result.pop()
    return result
    # findall_expands


def alphanum_range_expand( ss_l ):
    ret = []
    for sss in ss_l:
        # single alpha check 1st so {a-f} is not mistaken for
        # integer (not hex) numeric expand
        if re_1alpha.search( sss ):
            start = re_1alpha.match_obj.group(1)
            end   = re_1alpha.match_obj.group(2)
            end   = chr(ord(end)+1)
            while start != end:
                ret.append( start )
                start = chr(ord(start)+1)
        elif re_numeric.search( sss ):
            start = re_numeric.match_obj.group(1)
            end   = re_numeric.match_obj.group(2)
            bb    = re_numeric.match_obj.group(3)
            if   bb == None:
                for num in range(int(start),eval(end)+1):
                    ret.append( '%0*d'%(len(start),num) )
            elif bb == '0':
                for num in range(eval('0%s'%(start,)),eval(end)+1):
                    ret.append( '%0*o'%(len(start),num) )
            elif bb == '0x':
                for num in range(eval('0x%s'%(start,)),eval(end)+1):
                    ret.append( '%0*x'%(len(start),num) )
        else: ret.append( sss )
    TRACE( 17, 'alphanum_range_expand returning %s', ret )
    #print('alphanum_range_expand: %s returns %s'%(ss_l,ret) )
    return ret
    # alphanum_range_expand

# return a list of nodes
def expand( espec, explvl=0 ):
    import string
    import re
    TRACE( 18, 'expand(%s)', espec )
    #print( 'expand%d: espec=%s'%(explvl,espec) )
    especIn = espec
    try:
        placeholder_idx = 0
        expands = findall_expands( espec )
        exp_result = []
        for exp in expands:
            espec = espec.replace( exp, '<%d>'%(placeholder_idx,), 1 )
            placeholder_idx = placeholder_idx + 1
            pass
        # At this point, expands=list_of_expands, espec has expands replaced with <0>,<1>,...
        #print( 'expand%d: placeholder espec=%s'%(explvl,espec) )
        # But a specific placeholder may correspond to a nested expand.
        placeholder_idx = 0
        for sss in espec.split(','):
            TRACE( 19, 'expand sss=%s of espec=%s', sss, espec )
            place_holders = re.findall( '<[0-9]+>', sss )  # look for place holders
            #print('expand%d: sss=%s of espec=%s place_holders=%s'%(explvl,sss,espec,place_holders) )
            # the following "for loop" only occurs of there are place holders
            for idx in range(len(place_holders)):
                p_holder = '<%d>'%(placeholder_idx+idx,)
                #print('expand%d: call expand on the "value of the expand spec" i.e. "a-c" of {a-c}'%(explvl,) )
                expanding = expand( expands[placeholder_idx+idx][1:-1],explvl+1 ) #Recursive call - find nested expand specs.
                expanding = alphanum_range_expand( expanding )
                #print('expand%d: expanding=%s'%(explvl,expanding) )
                result = []
                for ssss in sss.split(','):
                    holder_idx = ssss.find(p_holder)
                    if holder_idx != -1:
                        pre = ssss[:holder_idx]
                        post= ssss[holder_idx+len(p_holder):]
                        for expanded in expanding:
                            result.append( pre+expanded+post )
                            #print('expand%d: p_holder=%s result=%s'%(explvl,p_holder,result))
                            pass
                        pass
                    #else: print('expand%d: no p_holder; result=%s'%(explvl,result))
                    pass
                sss = ','.join(result)
                pass
            #print('expand%d: now sss=%s from place_holders=%s'%(explvl,sss,place_holders))
            if sss!='' and place_holders == []:
                #print('expand%d: sss=%s from place_holders=%s COULD CHECK FILE HERE'%(explvl,sss,place_holders))
                retl = find_node_list_from_file( sss )
                if retl == [] and sss.find('/') != -1:
                    sys.stderr.write('invalid farmlet path %s (not a file or not readable)\n'%(sss,))
                    return []
                elif retl == []: exp_result = exp_result + sss.split(',')
                else:            exp_result = exp_result + retl
            elif sss != '':
                #print('expand%d: call expand on the %s non-empty place_holders (maybe file)'%(explvl,sss))
                exp_result = exp_result +  expand( sss,explvl+1 ) #Recursive call - find nested expand specs.
            else:
                # tack on the ['']
                exp_result = exp_result + sss.split(',')
                pass
            placeholder_idx = placeholder_idx + len(place_holders)
    except:  # any
        TRACE( 10, 'except - expand' )
        exc, value, tb = sys.exc_info()
        sys.stderr.write('Error expanding node list "%s": %s: %s\n'%(especIn,exc,value) )
        sys.stderr.write('Prehaps an invalid decimal/octal/hex digit?\n' )
        sys.stderr.write('Remember: in the \'{seq1-seq2}\' syntax, seq2 can begin\n' )
        sys.stderr.write('with \'0x\' to force hex or \'0\' to force octal.\n' )
        if g_opt['tlvlmsk']:
            for ln in traceback.format_exception( exc, value, tb ):
                sys.stderr.write(ln)
        sys.exit(1)

    return exp_result
    # expand, alphanum_range_expand, findall_expands


def node_list_from_spec( spec ):
    """\
    first check if special stdin indicator
    then process potentially expandable list.
        This can be a comma separated list of potentially expandable nodes OR
        "farmlet" files.
    """
    mach_l = []
    TRACE( 15, 'node_list_from_spec spec=%s', spec)
    if spec == '-':
        xx,sts = try_line( sys.stdin.fileno() )
        TRACE( 15,'node_list_from_spec xx=%s type(xx)=%s',xx,type(xx))
        while xx != b'.\n' and xx != b'':
            if re_mach.search(xx.decode('utf-8')): mach_l.append(re_mach.match_obj.group(1))
            xx,sts = try_line( sys.stdin.fileno() )
    else:
        #check for invalid node spec char(s)
        #if spec.find('/') != -1:
        #    sys.stderr.write('invalid farmlet path (not a file or not readable)\n')
        #    return []
        #if g_opt['verbose']: sys.stderr.write('assuming expandable node list\n')
        if g_opt['verbose']: sys.stderr.write('processing node spec (potential expansion)\n')
        mach_l = expand( spec )
    TRACE( 9,'node_list_from_spec - returning len(mach_l)=%d mach_l[0]=%s type(mach_l[0])=%s', len(mach_l), mach_l[0], type(mach_l[0]) )
    return mach_l
#-node_list_from_spec



def build_quoted_str( args ):
    import string                       # join
    quoted_args=[]
    for arg in args:
        if repr(arg)[0] == "'": quoted_args.append( "'%s'"%(arg,) )
        else:                   quoted_args.append( '"%s"'%(arg,) )
    return ' '.join( quoted_args )
    # build_quoted_str

def build_sh_single_quoted_str( i_str ):
    o_str = re.sub("'","<<0>>",i_str,0)
    o_str = re.sub("<<0>>",'\'"\'"\'',o_str,0)
    o_str = "'%s'"%(o_str,)
    return (o_str)
    # build_sh_single_quoted_str

def build_sh_doubly_single_quoted_str( i_str ):
    o_str = re.sub("'","<<0>>",i_str,0)
    o_str = re.sub("<<0>>",'\'"\'"\'',o_str,0)
    return (o_str)
    # build_sh_doubly_single_quoted_str

# this routine needs:
# g_opt={'tlvlmsk':0,'pty':''}
g_num_spawns = 0
def spawn( cmd, args, combine_stdout_stderr=0 ):
    import os                           # fork, pipe
    import pty                          # fork
    import string                       # split
    global g_num_spawns                 # keep track for total life of process
    
    g_num_spawns = g_num_spawns + 1
    cmd_list = cmd.split()    # support cmd='cmd -opt'

    # for stdin/out/err for new child. Note: (read,write)=os.pipe()
    if g_opt['pty']: pipe0 = [0,0]    ; pipe1 = [1,1];     pipe2 = os.pipe()
    else:            pipe0 = os.pipe(); pipe1 = os.pipe(); pipe2 = os.pipe()
    
    if g_opt['pty']: pid,fd = pty.fork()
    else:            pid    =  os.fork()
    
    if pid == 0:
        #child
        signal.signal(signal.SIGQUIT,signal.SIG_IGN)
        # combining stdout and stderr helps (when simply printing output)
        # get the output in the same order
        if combine_stdout_stderr: os.dup2( pipe1[1], 2 ); os.close( pipe2[1] )#; TRACE( 20, "child close %d", pipe2[1]) # close either way as we
        else:                     os.dup2( pipe2[1], 2 ); os.close( pipe2[1] )#; TRACE( 20, "child close %d", pipe2[1])  # are done with it.
        if g_opt['pty']:
            pass                        # all done for use in pyt.fork() (except our combining above)
        else:
            os.close( pipe0[1] )#; TRACE( 20, "child close %d", pipe0[1] )
            os.close( pipe1[0] )#; TRACE( 20, "child close %d", pipe1[0] )
            os.close( pipe2[0] )#; TRACE( 20, "child close %d", pipe2[0] )
            os.dup2( pipe0[0], 0 ); os.close( pipe0[0] )#; TRACE( 20, "child close %d", pipe0[0] )
            os.dup2( pipe1[1], 1 ); os.close( pipe1[1] )#; TRACE( 20, "child close %d", pipe1[1] )
        for ii in range(3,750):  # if default nway=200, and there are 3 fd's per process...
            try: os.close(ii)#; TRACE( 20, "child successfully closed %d", ii )
            except: pass # TRACE( 10, 'except - os.close(3-750) - spawn' )
            pass            

        try: os.execvp( cmd_list[0], cmd_list+args ) # bye-bye python
        except:  # From doc: Errors will be reported as OSError exceptions.
            msg='Error execing %s\n'%(cmd_list[0],)
            os.write( 2, msg.encode('utf-8') )
            sys.exit( 1 )
        pass
    #parent
    TRACE( 20, 'spawn: pid=%d p0=%s p1=%s p2=%s execvp( %s, %s )', pid, pipe0, pipe1, pipe2, cmd_list[0], cmd_list+args )
    if g_opt['pty']:
        pipe0[1] = fd               # stdin  (fd is read/write and only valid in parent; pty takes care of child stdin )
        pipe1[0] = fd               # stdout (fd is read/write and only valid in parent; pty takes care of child stdout )
        os.close( pipe2[1] )        # parent doesn't need to write to child's stderr (pty does not take care of stderr)
    else:
        os.close( pipe0[0] )        # parent doesn't need to read from child's stdin
        os.close( pipe1[1] )        # parent doesn't need to write to child's stdout
        os.close( pipe2[1] )        # parent doesn't need to write to child's stderr
    child_stdin  = pipe0[1]
    child_stdout = pipe1[0]
    if combine_stdout_stderr: child_stderr = None
    else:                     child_stderr = pipe2[0]
    return pid,child_stdin,child_stdout,child_stderr
    # spawn


# node_info == g_internal_info[x]
def spawn_cmd( node_info, mach_idx, opts, args, branch_nodes, do_local ):
    import os.path                      # basename, isdir
    import os                           # environ
    global g_mach_idx_offset            # declaration necessary because I'm setting it
    global g_connects_expected          # declaration necessary because I'm setting it
    TRACE( 21, 'spawn_cmd mach_idx=%d args=%s', mach_idx, args )
    if   g_opt['c']:
        # rgang COPY mode
        dest = args[-1]
        # do special $RGANG_MACH_ID processing
        # 3 cases: 1 for \"initiator\" node (adjust-copy-args='')
        #          2 for non-initiator node (adjust-copy-args='1' and '2')
        if g_opt['adjust-copy-args']:
            g_opt['adjust-copy-args'] = ''  # do this once, not for each branch
            sour = args[-1]
            if re_mach_id.search(sour): sour = '%s%d%s'%(re_mach_id.match_obj.group(1),g_mach_idx_offset,re_mach_id.match_obj.group(3))
            for ii in range(len(args[:-1])):
                if os.path.isdir(dest):
                    if sour[-1] == '/': args[ii] = sour+os.path.basename(args[ii])
                    else:               args[ii] = sour+'/'+os.path.basename(args[ii])
                else:
                    # THERE SHOULD BE JUST ONE
                    args[ii] = sour
            g_mach_idx_offset = g_mach_idx_offset + 1 # TRICKY - correct effects dest node processing and rgang --mach_idx_offset
        if re_mach_id.search(dest): dest = '%s%d%s'%(re_mach_id.match_obj.group(1),g_mach_idx_offset+mach_idx,re_mach_id.match_obj.group(3))

        if node_info['stage'] == None:
            # RECALL: rcp is always first; when there are multiple nodes
            # per branch, rgang uses a 2 step process - 1st/always rcp, then
            # 2nd, rsh the rgang (if it were one node, we could just rsh, but
            # for the stake of simplicity, when just use/rely on rgang).
            sp_args = args[:-1]+['%s:%s'%(node_info['ret_info']['name'],dest)]
            if g_opt['p']: sp_args = ['-p']+sp_args
            if g_opt['x']: sp_args = ['-x']+sp_args
            if g_opt['X']: sp_args = ['-X']+sp_args
            if g_opt['F']: sp_args = ['-F']+sp_args
            if g_opt['N']: sp_args = ['-N']+sp_args
            TRACE( 22, 'spawn_cmd rcp sp_args=>%s<', sp_args )
            sp_info = spawn( g_opt['rcp'], sp_args, g_opt['combine'] )
            node_info['stage'] = 'rcp'
            timeout_add( node_info['gbl_branch_idx'], float(g_opt['rcpto']) )
        else:
            # assume stage is rgang; it would be stage==rcp (with additional
            # node(s))
            sp_args = []
            if g_opt['l']: sp_args = sp_args + ['-l',g_opt['l']]
            if g_opt['x']: sp_args = sp_args + ['-x']
            if g_opt['X']: sp_args = sp_args + ['-X']
            if g_opt['f']: sp_args = sp_args + ['-f']
            if g_opt['F']: sp_args = sp_args + ['-F']
            if g_opt['N']: sp_args = sp_args + ['-N']
            sp_args = sp_args + [node_info['ret_info']['name']]
            q_user_arg_s     = build_quoted_str( args )
            sp_args = sp_args + [g_opt['sh'],'-c']
            # HERE'S THE 1ST PLACE WHERE I NEED TO ADD CONNECT_MAGIC
            sh_cmd_s = "'"  # I want only sh to interpret things
            sh_cmd_s = sh_cmd_s+'echo %s;'%(CONNECT_MAGIC,)
            g_connects_expected = g_connects_expected + 1
            sh_cmd_s = sh_cmd_s+'PATH=%s:$PATH;'%(g_opt['path'],)  # see option init
            sh_cmd_s = sh_cmd_s+'RGANG_MACH_ID=%d;export RGANG_MACH_ID;'%(mach_idx+g_mach_idx_offset,)
            sh_cmd_s = sh_cmd_s+'if [ -r $HOME/.rgangrc ];then . $HOME/.rgangrc;fi;' # stdout from .rgangrc should be OK; I search for PICKLE:
            sh_cmd_s = sh_cmd_s+'%s '%(g_opt['app'],)
            sh_cmd_s = sh_cmd_s+'--pypickle --mach_idx_offset=%d --adjust-copy-args '%(g_mach_idx_offset+mach_idx,)
            for rgang_opt in opts:
                if rgang_opt.find('--mach_idx_offset') == 0: continue
                if rgang_opt.find('--pypickle')        == 0: continue
                if rgang_opt.find('--adjust-copy-args')== 0: continue
                # use build_quoted_str to preserve, i.e., --rsh="rsh -F" (which is
                # equiv to "--rsh=rsh -F")
                sh_cmd_s = sh_cmd_s+build_sh_doubly_single_quoted_str(build_quoted_str([rgang_opt]))+' '

            sh_cmd_s = sh_cmd_s+'- %s'%(build_sh_doubly_single_quoted_str(q_user_arg_s),)

            sh_cmd_s = sh_cmd_s+"'"  # end the sh cmd string

            TRACE( 22, 'spawn_cmd rcp rgang sh_cmd_ss=>%s<', sh_cmd_s )

            sp_args = sp_args + [sh_cmd_s]
            sp_info = spawn( g_opt['rsh'], sp_args, 0 )  # never combine stderr/out of rsh rgang
            try:
                for machine in branch_nodes: os.write( sp_info[1], (machine+'\n').encode('utf-8') )
                os.write( sp_info[1], b'.\n' )
            except OSError: pass # let select (get_output) deal with the trouble
            node_info['stage'] = 'rgang'
            timeout_add( node_info['gbl_branch_idx'], float(g_opt['rshto']) )
    elif len(branch_nodes) == 1 and do_local and g_thisnode.is_me(branch_nodes[0]): # local, no need to rsh to ourselves
        sh_cmd_s = ''
        sh_cmd_s = sh_cmd_s+'RGANG_MACH_ID=%d;export RGANG_MACH_ID;'%(mach_idx+g_mach_idx_offset,)
        # RGANG_INITIATOR, RGANG_PARENT, RGANG_PARENT_ID, and RGANG_NODES should already be set
        sh_cmd_s = sh_cmd_s+'if [ -r $HOME/.rgangrc ];then . $HOME/.rgangrc;fi;'
        sh_cmd_s = sh_cmd_s+' '.join(args)
        TRACE( 22, 'spawn_cmd local sh_cmd_ss=>%s<', sh_cmd_s )
        sp_args = ['-c',sh_cmd_s]
        sp_info = spawn( g_opt['sh'], sp_args, g_opt['combine'] )
        node_info['stage'] = 'local'
    elif len(branch_nodes) == 1: # rsh
        sp_args = []
        if g_opt['l']: sp_args = sp_args + ['-l',g_opt['l']]
        if g_opt['x']: sp_args = sp_args + ['-x']
        if g_opt['X']: sp_args = sp_args + ['-X']
        if g_opt['f']: sp_args = sp_args + ['-f']
        if g_opt['F']: sp_args = sp_args + ['-F']
        if g_opt['N']: sp_args = sp_args + ['-N']
        sp_args = sp_args + [node_info['ret_info']['name']]
        q_user_arg_s     = build_quoted_str( args )
        sp_args = sp_args + [g_opt['sh'],'-c'] # NOTE: I cannot use 'exec','sh'... b/c
        # of "&& echo..." appended below. And "&& echo..." needs to be appended
        # after sh -c 'cmd' (as opposed to to the end of cmd) b/c usr cmd
        # might end w/ "&"
        # HERE'S THE 2ND PLACE WHERE I NEED TO ADD CONNECT_MAGIC
        sh_cmd_s = "'"  # I want only sh to interpret things
        sh_cmd_s = sh_cmd_s+'echo %s;'%(CONNECT_MAGIC,)
        g_connects_expected = g_connects_expected + 1
        sh_cmd_s = sh_cmd_s+'RGANG_MACH_ID=%d;export RGANG_MACH_ID;'%(mach_idx+g_mach_idx_offset,)
        sh_cmd_s = sh_cmd_s+'RGANG_INITIATOR=%s;export RGANG_INITIATOR;'%(os.environ['RGANG_INITIATOR'],)
        sh_cmd_s = sh_cmd_s+'RGANG_PARENT=%s;export RGANG_PARENT;'%(g_thisnode.hostnames_l[0],)
        sh_cmd_s = sh_cmd_s+'RGANG_PARENT_ID=%s;export RGANG_PARENT_ID;'%(g_thisnode.mach_idx,)
        sh_cmd_s = sh_cmd_s+'RGANG_NODES=%s;export RGANG_NODES;'%(os.environ['RGANG_NODES'],)
        sh_cmd_s = sh_cmd_s+'if [ -r $HOME/.rgangrc ];then . $HOME/.rgangrc;fi;'

        sh_cmd_s = sh_cmd_s+build_sh_doubly_single_quoted_str(' '.join(args))

        sh_cmd_s = sh_cmd_s+"'"  # end the sh cmd string

        TRACE( 22, 'spawn_cmd rsh mach_idx=%d sh_cmd_s=>%s<', mach_idx, sh_cmd_s )

        sp_args = sp_args + [sh_cmd_s]
        # So, the total command will be something like:
        #   rsh nn "sh -c 'cmd_will_exit_with_sts_x' && echo ST_0 || echo ST_1"
        # 1st, old rsh returned exit sts was not that of the cmd, so need to
        # echo a sts -- but there is no all-shells compatible way (shell
        # agnostic) to echo the actual status and still support being able
        # to specify a backgrounding command (&) UNLESS I added yet another
        # sh -c wrapper:
        #   rsh nn "sh -c 'sh -c \"cmd\" && echo ST_0 || echo ST_$?'"
        # Add "" just so the re_status will not be found in ps output
        sp_args = sp_args+[' && echo %s""0 || echo %s""1'%(STATUS_MAGIC,STATUS_MAGIC)]

        sp_info = spawn( g_opt['rsh'], sp_args, g_opt['combine'] )
        node_info['stage'] = 'rsh'
        timeout_add( node_info['gbl_branch_idx'], float(g_opt['rshto']) )
    elif len(branch_nodes) >= 1: # rsh rgang  (not user command!)
        # need rsh <rsh_opts>... <node> <sh_cmd>
        #                 sh_cmd is appended/quoted_str of "sh -c 'python_n_rgangapp_path_var_set;rgang_app '"
        #                                                  ['"]quoted_rgang_opts['"]
        #                                                  "' - '"
        #                                                  ['"]quoted_user_args['"]
        sp_args = []
        if g_opt['l']: sp_args = sp_args + ['-l',g_opt['l']]
        if g_opt['x']: sp_args = sp_args + ['-x']
        if g_opt['X']: sp_args = sp_args + ['-X']
        if g_opt['f']: sp_args = sp_args + ['-f']
        if g_opt['F']: sp_args = sp_args + ['-F']
        if g_opt['N']: sp_args = sp_args + ['-N']
        if g_opt['ditto']: sp_args = sp_args + ['--ditto']
        sp_args = sp_args + [node_info['ret_info']['name']]
        q_user_arg_s     = build_quoted_str( args )
        sp_args = sp_args + [g_opt['sh'],'-c']
        # HERE'S THE 3RD PLACE WHERE I NEED TO ADD CONNECT_MAGIC
        sh_cmd_s = "'"  # I want only sh to interpret things
        sh_cmd_s = sh_cmd_s+'echo %s;'%(CONNECT_MAGIC,)
        g_connects_expected = g_connects_expected + 1
        sh_cmd_s = sh_cmd_s+'PATH=%s:$PATH;'%(g_opt['path'],)  # see option init
        sh_cmd_s = sh_cmd_s+'RGANG_MACH_ID=%d;export RGANG_MACH_ID;'%(mach_idx+g_mach_idx_offset,)
        sh_cmd_s = sh_cmd_s+'RGANG_INITIATOR=%s;export RGANG_INITIATOR;'%(os.environ['RGANG_INITIATOR'],)
        sh_cmd_s = sh_cmd_s+'RGANG_PARENT=%s;export RGANG_PARENT;'%(g_thisnode.hostnames_l[0],)
        sh_cmd_s = sh_cmd_s+'RGANG_PARENT_ID=%s;export RGANG_PARENT_ID;'%(g_thisnode.mach_idx,)
        sh_cmd_s = sh_cmd_s+'RGANG_NODES=%s;export RGANG_NODES;'%(os.environ['RGANG_NODES'],)
        sh_cmd_s = sh_cmd_s+'if [ -r $HOME/.rgangrc ];then . $HOME/.rgangrc;fi;' # stdout from .rgangrc should be OK; I search for PICKLE:
        sh_cmd_s = sh_cmd_s+'%s '%(g_opt['app'],)
        sh_cmd_s = sh_cmd_s+'--pypickle --mach_idx_offset=%d '%(g_mach_idx_offset+mach_idx,)
        for rgang_opt in opts:
            if rgang_opt.find('--mach_idx_offset') == 0: continue
            if rgang_opt.find('--pypickle')        == 0: continue
            # use build_quoted_str to preserve, i.e., --rsh="rsh -F" (which is
            # equiv to "--rsh=rsh -F")
            sh_cmd_s = sh_cmd_s+build_sh_doubly_single_quoted_str(build_quoted_str([rgang_opt]))+' '

        sh_cmd_s = sh_cmd_s+'- '    # "-" is the nodespec

        for arg_s in args:
            sh_cmd_s = sh_cmd_s+build_sh_doubly_single_quoted_str( build_sh_single_quoted_str(arg_s) ) + ' '

        sh_cmd_s = sh_cmd_s+"'"  # end the sh cmd string

        TRACE( 22, 'spawn_cmd rgang sh_cmd_s=>%s<', sh_cmd_s )

        sp_args = sp_args + [sh_cmd_s]
        sp_info = spawn( g_opt['rsh'], sp_args, 0 )  # never combine stderr/out of rsh rgang
        TRACE( 23, 'spawn_cmd sending %d nodes: %s', len(branch_nodes), branch_nodes )
        try:
            for ii in range(len(branch_nodes)):
                machine = branch_nodes[ii]
                TRACE( 23, 'spawn_cmd sending node %s type(machine)=%s to fd=%d', machine,type(machine), sp_info[1])
                if PY3_: os.write( sp_info[1], str.encode(machine)+b'\n' )
                else:    os.write( sp_info[1], machine+'\n' )
            os.write( sp_info[1], b'.\n' )
        except:
            EClass,detail = sys.exc_info()[:2]
            if EClass is OSError:
                errn = detail.errno
                fd=sp_info[1]
                if errn == errno.EPIPE:
                    TRACE( 10, 'OSError EPIPE exception writing node_l fd=%d',fd )
                else: TRACE( 10, 'OSError %d exception writing node_l',errn )
                pass
            else: TRACE( 23, 'spawn_cmd EClass is %s', EClass )
            pass
        node_info['stage'] = 'rgang'
        timeout_add( node_info['gbl_branch_idx'], float(g_opt['rshto']) )
    else:                        # program error
        raise ProgramError('unexpected branch_nodes list len=%s'%(len(branch_nodes),))
    return sp_info   #pid,child_stdin,child_stdout,child_stderr
    # spawn_cmd, spawn


def get_nway_indexes( nway, nth, list_length, minus_idx0=0 ):
    if minus_idx0: minus_idx0=1; list_length = list_length - 1
    split_num = float(list_length) / nway
    start     = int( ((nth)*split_num)+0.5 ) + minus_idx0
    end       = int( ((nth+1)*split_num)+0.5 ) + minus_idx0
    TRACE( 23, 'get_nway_indexes(nway=%s,nth=%s,list_length=%s,minus_idx0=%s)=(start=%s,end=%s)',
           nway, nth, list_length, minus_idx0, start, end )
    return start,end
    # get_nway_indexes


def set_connected_g( mach_idx, to_state ):
    global g_num_connects, g_connects_expected
    if to_state == 0:
        # it may or may not be connected (so check with "if")
        if g_internal_info[mach_idx]['connected'] == 1: g_num_connects -= 1
        g_connects_expected -= 1
    else:
        # it should not already be connected (no need to check with "if")
        g_num_connects += 1
        pass
    g_internal_info[mach_idx]['connected'] = to_state
    return None


def header( machine, args, idx ):
    if   g_opt['n'] == '1':
        if g_opt['verbose']: sys.stdout.write( "%5d %s= "%(idx,machine) )
        else:                sys.stdout.write( "%s= "%(machine,) )
    elif g_opt['n'] == '2' or g_opt['n'] == '3':   sys.stdout.write( "\n\
- - - - - - - - - - - - - - %s - - - - - - - - - - - - - -\n"%(machine,) )
    if g_opt['c'] and g_opt['n']=='3':
        sp_args = args[:-1]+['%s:%s'%(machine,args[-1])]
        sys.stdout.write( '%s %s\n'%(g_opt['rcp'],' '.join(sp_args)) )
    elif not g_opt['c'] and g_opt['n']=='3':
        sys.stdout.write( '%s %s %s\n'%(g_opt['rsh'],machine,build_quoted_str(args)) )
    sys.stdout.flush()
    # header


# interruptible select
#import select,errno
def select_interrupt( rr, ww, ee, wait ):
    while 1:
        try: ready = select.select( rr, ww, ee, wait )
        except:
            exc, value = sys.exc_info()[:2]
            TRACE( 10, 'except - select - get_output - exc=%s value=%s', exc, repr(value) )
            if exc is select.error:
                exec('vv='+value.__str__()) # this is "problem" if exc not select.error
                if vv[0]==errno.EINTR: continue
            raise
        break
    return ready


# returns bytes,status where:
#    status=0 == line
#    status=1 == tmo
#    status=2 == eof
def try_line( fd ):
    import os
    sts = 0
    while 1:
        try:
            #final_b = bb = fd.read( 1 )
            #final_b = bb = os.read(fd.fileno(), 1 )
            final_b = bb = os.read(fd, 1 )
        except:
            ee,detail=sys.exc_info()[:2]
            if ee is IOError:
                TRACE( 10, 'except - read - try_line errno=%d', detail.errno )
                if detail.errno in (errno.EINTR,): continue
                pass
            # any error - THIS CAN MESS UP ^C (main()'s except KeyboardInterrupt...)
            TRACE( 10, 'except - read - try_line' )
            return b'',2
        break
    try:
        TRACE( 24, 'try_line looking for line' )
        while bb != b'\n' and bb != b'':
            rr,ww,ee = select_interrupt([fd],[],[],0.9)
            if not rr: sts=1;break
            #bb = fd.read( 1 )
            #bb = os.read(fd.fileno(), 1 )
            bb = os.read( fd, 1 )
            final_b = final_b + bb
        if bb == b'': sts=2
    except:   # ??????
        TRACE( 10, 'excpet - select - try_line' )
        sys.stderr.write( 'while... fd=%s\n'%(fd,) )
        #sys.exit( 1 )
        exc, value = sys.exc_info()[:2]
        raise exc(value)
    TRACE( 25, 'try_line returning %s', (final_b,sts) )
    return final_b,sts
    # try_line


def get_output( sel_l, fo2node, wait ):
    import select
    import os
    global g_num_connects               # because I'm modifying it

    mach_idx=-1; bb=b'' # init for TRACE below
    chk_exit=0; final_b=b''; fd=None; sh_exit_status=None
    while 1: # debugging (EAGAIN; see below)
        #if sys.stdin in sel_l: TRACE( 26, 'get_output select checking stdin' )
        #TRACE( 26, 'get_output sel_l=%s wait=%s', sel_l, wait )

        ready = select_interrupt( sel_l, [], sel_l, wait )

        #TRACE( 27, 'get_output ready is %s', ready )
        if not ready[0]:
            # timeout (or error, but assume timeout; I'm not processing errors)
            if ready[2]: raise ProgramError('select error')
            break

        fd = ready[0][0]
        mach_idx = fo2node[fd]['mach_idx']

        #if   fo2node[fd]['std'] == sys.stdout.fileno():
        #    TRACE( 27, 'get_output select processing for mach_idx=%d stdout', mach_idx )
        #elif fo2node[fd]['std'] == sys.stderr.fileno():
        #    TRACE( 27, 'get_output select processing for mach_idx=%d stderr', mach_idx )
        #else:
        #    TRACE( 27, 'get_output select processing for mach_idx=%d main stdin', mach_idx )
        # NOTE: When in pty mode, the input is NOT echoed locally and
        #       currently it will take time to check for the STATUS_MAGIC
        #       before echoing the typed characters.
        try:
            # data destined for stdout could have "imbedded magic cookies"
            # which requires trying to get a "lines" worth of data -- at
            # certain "stages"
            # ['stage'] should be (see spawn_cmd) one of:
            #  copy-mode:
            #       'rcp'
            #       'rgang'    need "connect"
            #  cmd-mode:
            #       'local'
            #       'rsh'      need "connect" ,then "status"
            #       'rgang'    need "connect" ,then pickle
            if    fo2node[fd]['std'] == sys.stdout.fileno() \
               and ( g_internal_info[mach_idx]['stage'] == 'rsh' \
                     or (g_internal_info[mach_idx]['stage'] == 'rgang' \
                         and g_internal_info[mach_idx]['connected'] == 0 )):
                bb,sts = try_line( fd )
            else:
                # Could also be main stdin
                final_b = os.read( fd, 8192 )
                if not final_b: chk_exit = 1
                return chk_exit, final_b, fd, mach_idx, sh_exit_status
        except:
            ee, detail = sys.exc_info()[:2]
            if ee is IOError:
                TRACE( 10, 'except - read - get_output' )
                if detail.errno == 11: sys.stderr.write( "EAGAIN\n" ); continue
                else: raise IOError(detail)
            else: raise
        #TRACE( 31, "get_output mach_idx=%d: ['stage']=%s connect=%s bb=>%s<"
        #       , mach_idx, g_internal_info[mach_idx]['stage'], g_internal_info[mach_idx]['connected'], bb )

        if bb:
            if    fo2node[fd]['std'] == sys.stdout.fileno():
                if ( g_internal_info[mach_idx]['stage'] == 'rsh' \
                      or g_internal_info[mach_idx]['stage'] == 'rgang') \
                         and g_internal_info[mach_idx]['connected'] == 0:
                    # Look for the STATUS_MAGIC or CONNECT_MAGIC.
                    # NOTE! THERE IS THE SMALL POSSIBILITY THAT THIS PROCESSING
                    # WILL FAIL B/C THE OF A DELAY IN THE TRANSMISSION OF THE
                    # STATUS LINE (GREATER THAN THE TIMEOUT IN THE TRY_LINE
                    # FUNCTION ABOVE)
                    if re_connect.search( bb.decode("utf-8") ):
                        TRACE( 29, 'get_output mach_idx=%d: yes connect magic', mach_idx )
                        final_b = re_connect.match_obj.group(1).encode()
                        set_connected_g( mach_idx, 1 )
                        timeout_cancel( g_internal_info[mach_idx]['gbl_branch_idx'] )
                    else:
                        final_b = bb
                elif g_internal_info[mach_idx]['stage'] == 'rsh': # and connected
                    if re_status.search( bb.decode("utf-8") ):
                        TRACE( 29, 'get_output mach_idx=%d: yes status magic', mach_idx )
                        final_b = re_status.match_obj.group(1).encode()
                        sh_exit_status = int(re_status.match_obj.group(2))
                    else:
                        final_b = bb
                else: # either rcp, local or (rgang and connected)
                    final_b = bb
            else:
                final_b = bb
            break
        else:
            chk_exit = 1
        break
    #TRACE( 31, 'get_output mach_idx=%d fd=%s chk_exit=%s sh_exit_status=%s returning (bb=%s) >%s<',
    #       mach_idx,fd,chk_exit,sh_exit_status,bb,final_b )
    return chk_exit, final_b, fd, mach_idx, sh_exit_status
    # get_output



def get_stderr_output( ret_info, fo2node_map, mach_idx, processing_idx, tmo=0 ):
    chk = 0; fo2 = g_internal_info[mach_idx]['sp_info'][3] # init this as fo may be None (i.e. tmo)
    while not chk and fo2 != None:
        chk,ss,fo2,mi,dont_used = get_output( [g_internal_info[mach_idx]['sp_info'][3]], # 3 is stdERR
                                              fo2node_map, tmo )
        if do_output( mach_idx, processing_idx, ret_info ):
            TRACE( 8, 'get_stderr_output: do_output(mach_idx=%d...) returned true',mach_idx )
            os.write( sys.stderr.fileno(), ss )
        else:
            ret_info[mach_idx]['stderr'] = ret_info[mach_idx]['stderr'] + ss
            pass
        if g_opt['ditto']: ret_info[mach_idx]['crc32'] = zlib.crc32(ss,ret_info[mach_idx]['crc32'])
        pass
    return chk



def do_output( mach_idx, processing_idx, ret_info ):
    if     mach_idx == processing_idx \
       and not g_opt['pyret'] \
       and g_internal_info[mach_idx]['stage'] != 'rgang':
        if not g_opt['ditto']: return 1
        else:
            if g_opt['mach_idx_offset']!='': return 1
            elif mach_idx==0: return 1
            elif ret_info[mach_idx]['rmt_sh_sts']!=None: return 1
            else: return 0
    else: return 0
    # do output


# separate out the pickled object from any "stdout" (i.e. from .rgangrc)
# and store it (if partial) in g_internal_info[mach_idx]['partial_pickle']
# NOTE: get_output (above) does some of this separating too
# basic algorithm is:
# try searching in last_few+ss   (last_few might be '')
#   if not found, determine if within the last few characters, if there is a
#     potential match and if there is, withhold/buffer those last few char
# last few could be "P"                 save "P"
#                   "PI"                save "PI"
#                   ...
#                   "PICKLE:"           save "PICKLE:"
#                   "PICKLE:1"          save "PICKLE:1"
#                   ...
#                   "PICKLE:1234567"    save "PICKLE:1234567"
#                   "PICKLE:12345678"   save "PICKLE:12345678"
#                   "PICKLE:12345678:"  save "PICKLE:12345678:"
#                   "xPICKLE:12345678"  save "PICKLE:12345678"
#                   "xxPICKLE:1234567"  save "PICKLE:1234567"
#                   ...
#                   "xxxxxxxxxxxxxPIC"  save "PIC"
#                   "xxxxxxxxxxxxxxPI"  save "PI"
#                   "xxxxxxxxxxxxxxxP"  save "P"
#  potential_idx = ss.rindex('P',-16)
#  potential = ss[potential_idx:]    # this would return 'Pxx' from 'xxxxxxxxxPxx'
#  then if 'PICKLE:'.find(potential) == 0:
#    out ss[:potential_partial]
#   sav/buffer ss[potential_partial:]
#  else out it all
def partial_pickle_cookie_check( chk_bytes ):
    chk_bytes_idx = chk_bytes.rfind(b'P',-(pickle_cookie_len-1))

    if chk_bytes_idx == -1:                          return -1,b''

    potential = chk_bytes[chk_bytes_idx:]

    pkl_len = len(b'PICKLE:')
    if b'PICKLE:'.find(potential[:pkl_len]) == -1:  return -1,b''

    if len(potential) <= pkl_len:                  return chk_bytes_idx,potential

    if re_hex.search( potential[pkl_len:].decode("utf-8") ):
        len_len = len(re_hex.match_obj.group(0))

        # check if wont have ending b':' (or b'\n' which if it did,
        #   this routine should not have been called)
        if   len(potential) <= pickle_cookie_len-2:
            if len_len == len(potential[pkl_len:]):return chk_bytes_idx,potential
            else:                                  return -1,b''
            pass
        else:
            if len_len != 8:                       return -1,b''
            if potential[-1] != b':':               return -1,b''
            else:                                  return chk_bytes_idx,potential
            pass
        pass
    else:                                          return -1,b''
    return -1,b''   # partial_pickle_cookie_check

def unpickle_and_add_to_ret_info( mach_idx, ret_info, pickle_str ):
    TRACE( 11, 'unpickle mach_idx=%d type(pickle_str)=%s', mach_idx, type(pickle_str) )
    try: loads = pickle.loads( pickle_str )
    except:
        exc, value, tb = sys.exc_info()
        TRACE( 11, 'unpickle_and_add_to_ret_info pickle.loads EXCEPTION %s', exc )
        return None

    if g_opt['c']: offset = 1
    else:          offset = 0

    for ii in range(len(loads)):
        ret_info[mach_idx+offset+ii]['rmt_sh_sts'] = loads[ii]['rmt_sh_sts']
        ret_info[mach_idx+offset+ii]['name']       = loads[ii]['name']
        TRACE( 11, "unpickle_and_add_to_ret_info type(ret_info[mach_idx+offset+ii]['stdout'])=%s type(loads[ii]['stdout'])=%s",
                                                 type(ret_info[mach_idx+offset+ii]['stdout']),   type(loads[ii]['stdout']) )
        if type(ret_info[mach_idx+offset+ii]['stdout']) != type(loads[ii]['stdout']):
              ret_info[mach_idx+offset+ii]['stdout']    += loads[ii]['stdout'].encode("utf-8")
        else: ret_info[mach_idx+offset+ii]['stdout']    += loads[ii]['stdout']
        if type(ret_info[mach_idx+offset+ii]['stderr']) != type(loads[ii]['stderr']):
              ret_info[mach_idx+offset+ii]['stderr']    += loads[ii]['stderr'].encode("utf-8")
        else: ret_info[mach_idx+offset+ii]['stderr']    += loads[ii]['stderr']
        ret_info[mach_idx+offset+ii]['crc32']      = loads[ii]['crc32']
        pass
    TRACE( 11, 'unpickle_and_add_to_ret_info completed mach_idx=%d offset=%d ii=%d', mach_idx, offset, ii )
    return None   # unpickle_and_add_to_ret_info

def dict_pop( dict, key, optional=None ):
    if optional==None: retval = dict[key]; del(dict[key]); return retval
    else:
        try: retval = dict[key]; del(dict[key]); return retval
        except (AttributeError,KeyError): pass
        pass
    return optional

def do_stage_rgang_processing( ss, mach_idx, ret_info ):
    if 0:
        ret_info[mach_idx]['stdout'] = ret_info[mach_idx]['stdout'] + ss
    else:
        branch_idx = g_internal_info[mach_idx]['gbl_branch_idx']
        branch_mach_head = g_branch_info_l[branch_idx]['active_head']
        branch_mach_end  = g_branch_info_l[branch_idx]['branch_end_idx']

        while 1:  # someday we may have intermediate (multiple) pickled results

            TRACE( 11,
                   'rgang looking for PICKLE (rmt_sh_sts=%s) len=%d >%.20s<',
                   ret_info[mach_idx]['rmt_sh_sts'], len(ss), ss )

            # first see if we are in the middle of a pickled string
            prt_pkl_str = dict_pop(g_internal_info[mach_idx],'part_pkl_loads','')
            if prt_pkl_str:
                TRACE( 11, 'continueing' )
                pickle_len = dict_pop( g_internal_info[mach_idx],'plk_len' )
                chk_str    = prt_pkl_str + ss
                pickle_str = chk_str[:pickle_len]
                ss         = chk_str[pickle_len:] # for next go round

                if len(pickle_str) != pickle_len:
                    TRACE( 11, 'save for later -- len(pickle_str)%d != %dpickle_len', len(pickle_str), pickle_len)
                    g_internal_info[mach_idx]['part_pkl_loads'] =pickle_str
                    g_internal_info[mach_idx]['plk_len']        =pickle_len
                    break
                # OK unpickle and add_to_ret_info
                unpickle_and_add_to_ret_info( mach_idx, ret_info, pickle_str )

            else:

                potential = dict_pop(g_internal_info[mach_idx],'part_pkl_cookie','')

                if potential: chk_str = potential + ss
                else:         chk_str = ss

                chk_str_deco = chk_str.decode("utf-8",'ignore') # needed for python3 node --nway=1 to python2 node ????
                if re_pickle.search(chk_str_deco):
                    pickle_len = int(re_pickle.match_obj.group(1),16)
                    if PY3_: pickle_idx = chk_str.find(str.encode(re_pickle.match_obj.group(0))) + pickle_cookie_len
                    else:    pickle_idx = chk_str_deco.find(re_pickle.match_obj.group(0)) + pickle_cookie_len
                    TRACE( 11, 'do_stage_rgang_processing re_pickle.match_obj.group(0)=%s pickle_len=%d pickle_idx=%d',
                           re_pickle.match_obj.group(0), pickle_len, pickle_idx )
                    pre        = chk_str[:pickle_idx-pickle_cookie_len]
                    pickle_str = chk_str[pickle_idx:pickle_idx+pickle_len]
                    ss         = pre + chk_str[pickle_idx+pickle_len:]

                    # What to do with pre??????????????????

                    if len(pickle_str) != pickle_len:
                        TRACE( 11, 'save for later -- done for now' )
                        g_internal_info[mach_idx]['part_pkl_loads'] =pickle_str
                        g_internal_info[mach_idx]['plk_len']        =pickle_len
                        break
                    # OK unpickle and add_to_ret_info
                    unpickle_and_add_to_ret_info( mach_idx, ret_info, pickle_str )

                else:
                    # check for partial
                    chk_str_idx,partial = partial_pickle_cookie_check( chk_str)
                    if partial:
                        g_internal_info[mach_idx]['part_pkl_cookie'] = partial
                        ss = chk_str[:chk_str_idx]
                    else:
                        ss = chk_str
                        pass
                    break
                pass
            pass
        pass
    TRACE( 11, 'do_stage_rgang_processing returning ss=>%s<',ss )
    return ss  # do_stage_rgang_processing


# sp_info = [pid,child_stdin,child_stdout,child_stderr]
def info_update( mach_idx, fo2node_map, sp_info, select_l ):
    # recall: sp_info=[pid,child_stdin,child_stdout,child_stderr]
    g_internal_info[mach_idx]['sp_info'] = sp_info
    if 1:
        fo2node_map[sp_info[1]] = {'mach_idx':mach_idx,'std':None}
        fo2node_map[sp_info[2]] = {'mach_idx':mach_idx,'std':sys.stdout.fileno()} # 'std' indicates data destined for stdout
        select_l.insert( 0, sp_info[2] )  # order matters; do not "append" after select_l[0] (main stdin)
    if sp_info[3]:
        fo2node_map[sp_info[3]] = {'mach_idx':mach_idx,'std':sys.stderr.fileno()} # 'std' indicates data destined for stderr
        select_l.insert( 0, sp_info[3] )  # order matters; do not "append" after select_l[0] (main stdin)
    # info_update


def info_clear( fd, fo2node_map, select_l ):
    TRACE( 2, "info_clear clearing fd=%s", fd )
    select_l.remove( fd )
    del( fo2node_map[fd] )
    os.close( fd )
    # info_clear

# this routine requires:
# g_timeout_l=[];g_opt={'c':1}
def timeout_add( gbl_br_idx, timeout_period ): # timeout_period is either float(g_opt['rshto'] or float(g_opt['rcpto']
    import time
    # b/c rcp time can be different, I need to search-add (list needs to be ordered)
    #
    expire_tm = time.time()+timeout_period
    if not g_opt['c']:          g_timeout_l.append( {'timeout_expires':expire_tm,'gbl_branch_idx':gbl_br_idx} )
    elif len(g_timeout_l) == 0: g_timeout_l.append( {'timeout_expires':expire_tm,'gbl_branch_idx':gbl_br_idx} )
    else: # copy mode, mix of rsh and rcp
        low_idx=0; high_idx=len(g_timeout_l)-1  # gaurd against len=0 above
        mid_idx = low_idx + int((high_idx - low_idx)/2)  # NOTE: python 2 vs 3 diff: in 2, 1/2 = int 0, in 3, it's float .5
        while mid_idx!=high_idx:
            if expire_tm < g_timeout_l[mid_idx]['timeout_expires']: high_idx = mid_idx
            else:                                                   low_idx = mid_idx+1 # no need to look at mid again
            mid_idx = low_idx + int((high_idx - low_idx)/2)
        if expire_tm < g_timeout_l[mid_idx]['timeout_expires']: new_idx = mid_idx
        else:                                                   new_idx = mid_idx+1
        g_timeout_l.insert( new_idx, {'timeout_expires':expire_tm,'gbl_branch_idx':gbl_br_idx} )
        pass
    pass
    # timeout_add

# currently OK if not found
def timeout_cancel( gbl_br_idx ):
    found = 0
    for idx in range(len(g_timeout_l)):
        if g_timeout_l[idx]['gbl_branch_idx'] == gbl_br_idx: found=1; g_timeout_l.pop(idx); break
    TRACE( 31, "timeout_cancel branch_idx=%d found=%d", gbl_br_idx, found )
    # timeout_cancel


# This handles 1 timeout - the 1st one!
def timeout_connect_process():
    import select                       # select
    branch_idx = g_timeout_l[0]['gbl_branch_idx']
    mach_idx = g_branch_info_l[branch_idx]['active_head']
    connected = g_internal_info[mach_idx]['connected']
    # recall: sp_info=[pid,child_stdin,child_stdout,child_stderr]
    pid       = g_internal_info[mach_idx]['sp_info'][0]
    g_timeout_l.pop(0)
    TRACE( 30, "timeout_connect_process branch_idx=%d connected=%d pidToKill=%d br_in=%s g_tmo_l=%s",
           branch_idx, connected, pid, g_internal_info[mach_idx]['sp_info'][1], g_timeout_l )

    # append ?something? to stderr
    ret_info = g_internal_info[mach_idx]['ret_info']
    ret_info['stderr'] = ret_info['stderr']+'rgang timeout expired\n'

    # do kill and kill check here
    for sig in (1,2,15,3,9):  # 1=HUP, 2=INT(i.e.^C), 15=TERM(default "kill"), 3=QUIT(i.e.^\), 9=KILL
        try: rpid,status = os.waitpid(pid,os.WNOHANG);status=(status>>8)  # but I probably won't use this status
        except:  # i.e. (OSError, '[Errno 10] No child processes')
            TRACE( 10, 'except - waitpid - timeout_connect_process' )
            rpid = 0
            break
        if rpid == pid:  # OK, process is out-of-there
            if g_internal_info[mach_idx]['ret_info']['rmt_sh_sts'] == None:
                TRACE( 31, "timeout_connect_process status=%d", status )
                g_internal_info[mach_idx]['ret_info']['rmt_sh_sts'] = 8
            break
        os.kill(pid,sig)
        TRACE( 31, "timeout_connect_process os.kill(%d,%d)", pid, sig )
        select_interrupt([],[],[],0.05)     # use select to sleep sub second

    return mach_idx  # need to return "chk_exit,..." like get_output
    # timeout_connect_process


def initiator_node_status( mach_idx ):
    # FIRST DETERMINE IF I AM THE INITIATOR NODE
    if g_opt['mach_idx_offset']=='' and g_opt['err-file']!='':
        sts = g_internal_info[mach_idx]['ret_info']['rmt_sh_sts']
        if sts != 0 and sts != None:
            TRACE( 28, 'initiator_node_status mach_idx=%d sts=%s', mach_idx,sts )
            fo = open( g_opt['err-file'], 'a+' )
            name = g_internal_info[mach_idx]['ret_info']['name']
            fo.write( "%s # mach_idx=%d sts=%s\n"%(name,mach_idx,sts) )
            fo.close()
    # initiator_node_status


def pickle_to_stdout( ret_info ):
    dumps = pickle.dumps(ret_info,protocol=2)
    cookie = b'PICKLE:%08x:\n'%(len(dumps),)   # make it a "line" for try_line
    ostr = cookie+dumps
    TRACE( 11, 'pickle_to_stdout len(ostr)=%d', len(ostr) )
    for ii in range(len(ret_info)):
        TRACE( 11, "pickle_to_stdout len(ret_info[%d][stdout])=%d len(ret_info[ii][stderr])=%d", ii, len(ret_info[ii]['stdout']), len(ret_info[ii]['stderr']) )
        ret_info[ii]['stdout'] = ret_info[ii]['stderr'] = b''
        pass
    #sys.stdout.write( ostr ); sys.stdout.flush()
    os.write(1,ostr)
    return None


def clean():
    #tty.setcbreak(0)
    os.system( "stty sane" )
    return
    # clean

def cleanup(signum,frame):
    clean()
    sys.exit( 1 )
    return
    # cleanup


def wait_nohang( pid ):
    # if no exception and no process exited, (0,0) is return (as per doc)
    TRACE( 5, "wait_nohang( pid=%s )", pid )
    for ii in range(3):   # potentially retry -- potential python/OS bug????
        try:
            rpid,rstatus = os.waitpid(pid,os.WNOHANG);rstatus=(rstatus>>8)
            break # no exception -- no retry
        except:  # i.e. (OSError, '[Errno 10] No child processes')
            exc, value = sys.exc_info()[:2]
            TRACE( 10, 'except - wait_nohang - waitpid(pid=%d) - %s %s %d'%(pid,exc,value,ii) )
            rpid = -1   # indicate exception
            rstatus=None
            #time.sleep(.1)
            pass
        pass
    return rpid,rstatus  # wait


g_opt={'tlvlmsk':0,'verbose':0,'farmlets':'.'}         # and init so test script importing
                                        # rgang (to test rgang.expand(),
                                        # for example) don't have to.
g_internal_info=[]                      # another (or the most) important global
g_ret_info=[]                           # global -- equiv to ret_info in rgang;available to main ^C exception
g_processing_idx=0                      # initialize in case fast ^C
g_grp_idxs=(0,0)                        # initialize in case fast ^C
g_thisnode = None                       # needed before 1st TRACE
g_mach_l=[]

def rgang( opts_n_args ):
    import os                           # system
    import signal                       # signal
    global g_opt
    global g_thisnode                   # 
    global g_timeout_l                  # 
    global g_internal_info              # 
    global g_branch_info_l              # 
    global g_mach_idx_offset            # 
    global g_processing_idx             # allow access from signal handler -- to print remaining output
    global g_grp_idxs                   # allow access from signal handler -- to print remaining output
    global g_mach_l                     # allow access from signal handler -- to print remaining output
    global g_args                       # allow access from signal handler -- to print remaining output
    global g_num_connects               # needed for robust "input-to-all-branches" see (get_output)
    global g_connects_expected          # needed for robust "input-to-all-branches" see (spawn_cmd and below)
    # --------------------------------- # NOTE: currently, there is the
    # possibility of a hang on the write to a branch if all nodes in
    # the rgang sub tree fail and stdin is large.

    opts,g_args,g_opt,usage = getopts( OPTSPEC, opts_n_args,USAGE,USAGE_V,APP )
    try: g_opt['tlvlmsk'] = int( eval(g_opt['tlvlmsk']) )  # 0x hex or normal decimal numbers OK
    except:
        TRACE( 10, 'except - tlvlmsk' )
        sys.stderr.write('invalid tlvlmsk value; must be integer/hex\n')
        return 1,[]
    TRACE( 3, 'rgang g_opt is %s', g_opt )

    if g_opt['path']!=DFLT_PATH and not DFLT_PATH in g_opt['path'].split(':'):
        g_opt['path'] += ':'+DFLT_PATH
        pass

    if g_opt['d']:
        c="ls %s"%(g_opt['farmlets'],); os.system(c); return 0,[]
    elif g_opt['list'] and not g_args:
        if os.access(g_opt['farmlets']+'/.',os.R_OK):
            c1="for i in *;do echo FARMLET $i:; cat $i;done"
            c="sh -c 'cd %s;%s'"%(g_opt['farmlets'],c1)
            os.system(c)
        else:
            sys.stdout.write( 'farmlets directory %s not readable\n'%(g_opt['farmlets'],) )
        return 0,[]
    if not g_args: sys.stdout.write( 'no args\n'+usage+'\n' ); return 0,[]

    g_mach_l = node_list_from_spec( g_args.pop(0) )
    if g_mach_l ==[]: return 1,[]

    g_thisnode = NodeInfo()

    if g_opt['pypickle'] and not (g_opt['pypickle'] in ('0','1')):
        sys.stderr.write('invalid argument for --pypickle\n'); return 1,[]
    if g_opt['pyprint']:  g_opt['pyret']='1'
    if g_opt['pypickle']: g_opt['pyret']='1'
    if g_opt['pypickle'] and g_opt['pyprint']: g_opt['pyprint']='' # pypickle wins
    # clean skips
    if g_opt['skip']:
        skip_l = node_list_from_spec( g_opt['skip'] )
        for sk in skip_l:
            ii = 0; mach_l_len = len( g_mach_l )
            while ii < mach_l_len:
                if g_mach_l[ii] == sk:
                    g_mach_l.pop(ii)
                    #break  # do this if I only want to remove the first occurrence of sk
                    mach_l_len = mach_l_len-1
                else: ii = ii + 1
    if g_opt['C']:        g_opt['s']='1'; g_opt['c']='1'
    if g_opt['s']:  # skip current (local) node
        ii = 0; mach_l_len = len( g_mach_l )
        while ii < mach_l_len:
            if g_thisnode.is_me(g_mach_l[ii]):
                g_mach_l.pop(ii); mach_l_len = mach_l_len - 1
            else: ii = ii + 1
    # g_mach_l is now set.

    if g_opt['list']:
        if not g_opt['pyret']:
            for mach_idx in range(len(g_mach_l)):
                mach = g_mach_l[mach_idx]
                # ref. initiator_node_status
                if g_opt['verbose']: sys.stdout.write( "%s # mach_idx=%d\n"%(mach,mach_idx) )
                else:                sys.stdout.write( "%s\n"%(mach,) )
                pass
            pass
        overall_status = 0; ret_info = g_mach_l # ret_info can have different formats
        if   g_opt['pyprint']:  pprint.pprint( ret_info )
        elif g_opt['pypickle']: pickle_to_stdout( ret_info )
        return overall_status,ret_info

    TRACE( 4, 'rgang args=>%s< opts=%s', g_args, g_opt )
    if g_opt['n'] == '':
        if len(g_mach_l) == 1: g_opt['n']='0'
        else:                g_opt['n']='1'
    elif g_opt['n'] == 'n': g_opt['n']='1'
    if len(g_opt['n'])>1 or not '0'<=g_opt['n']<='3':
        sys.stderr.write('invalid optional argument "%s" for -n option\n'%(g_opt['n'],))
        return 1,[]

    if g_opt['c'] and len(g_args) < 2:
        sys.stderr.write('copy mode must have at least 2 arguments\n')
        return 1,[]

    if len(g_args) == 0:
        sys.stderr.write('interactive not yet supported\n')
        return 1,[]

    try: nway = int( g_opt['nway'] ) # int(string)=>int and int(int)=>int
    except:
        TRACE( 10, 'except - nway' )
        sys.stderr.write('invalid nway value; must be integer >= 0\n')
        return 1,[]
    if nway < 0: sys.stderr.write('invalid nway value; must be integer >= 0\n');return 1,[]

    if g_opt['mach_idx_offset'] != '': # note: also used to determine initiator node
        try: g_mach_idx_offset = int( g_opt['mach_idx_offset'] ) # int(string)=>int and int(int)=>int
        except:
            TRACE( 10, 'except - mach_idx_offset' )
            sys.stderr.write('invalid mach_idx_offset value; must be decimal integer\n')
            return 1,[]
        g_thisnode.mach_idx = '%d'%(g_mach_idx_offset,) # for spawn_cmd rsh rgang
        g_opt['do-local'] = 1 # I'm assuming I've already rsh'd (rsh rgang...), so don't do rsh again
    else: # assume I'm the "initiator" node
        os.environ['RGANG_INITIATOR'] = g_thisnode.hostnames_l[0]
        # set the following now, in case we are also the root node and
        # opt['do-local']; this make spawn_cmd easier
        os.environ['RGANG_PARENT'] = ''
        os.environ['RGANG_PARENT_ID'] = ''
        os.environ['RGANG_NODES'] = str(len(g_mach_l))
        g_mach_idx_offset = 0 # for branches (see spawn_cmd)
        g_thisnode.mach_idx='' # for spawn_cmd rsh rgang; init for TRACE
        for ii in range(len(g_mach_l)):
            if g_thisnode.is_me(g_mach_l[ii]): g_thisnode.mach_idx='%d'%(ii,); break # for spawn_cmd rsh rgang
        if g_opt['err-file'] != '':   # init err-file
            try: fo = open( g_opt['err-file'], 'w+' )
            except: exc,val,tb=sys.exc_info(); sys.stderr.write('Problem with --err-file: %s\n'%(val)); return 1,[]
            TRACE( 2, "rgang err-file fd=%d", fo.fileno() )
            fo.close()

    mach_l_len = len( g_mach_l )
    if g_opt['serial']:
        if g_opt['input-to-all-branches']:
            sys.stderr.write('invalid --serial/--input-to-all-branches configuration\n');return 1,[]
            pass
        #                                        outer_nway will be "_number_of_ groups"  (the value of --nway)
        if g_opt['serial']=='0': inner_nway = 0; outer_nway = nway
        else:                    inner_nway = 0; outer_nway = int( math.ceil((mach_l_len/float(g_opt['serial']))) )
        #                                                      Value of g_opt['serial'] is "groups (at most) _of_".
        #             The last group may be a (small) partial "group _of_". Basically, the modulus, if non-zero.
        #             The value of --nway is ignored when g_opt['serial']!='0' (and !='')
    else:
        outer_nway = 1;    inner_nway = nway
    if outer_nway > mach_l_len or outer_nway == 0: outer_nway = mach_l_len  # inner_nway is handled below

    
    ####### OK done with ALL the OPTIONS PROCESSING

    if g_opt['pty']:
        signal.signal(2,cleanup)
        signal.signal(15,cleanup)
        os.system("stty -echo -icanon min 1 time 0" )
        os.system("stty -inlcr -icrnl" )      # no translations
        #os.system("stty ignbrk -ixon -isig" )
        os.system("stty ignbrk -ixon" )
        pass


    ####### NOW, DO THE WORK!!!!

    # could be counting > 2G bytes
    if sys.version_info[0] == 2: exec( 'stdin_bytes = 0L' )
    else:                        exec( 'stdin_bytes = 0' )
    # build/initialize the array so we can add stdin at the end
    ret_info = g_ret_info = []  # make ret_info g_ret_info
    g_internal_info=[]
    for ii in range(mach_l_len):
        ret_info.append({'name':g_mach_l[ii],'stdout':b'','stderr':b'','rmt_sh_sts':None,'crc32':0})
        g_internal_info.append({'gbl_branch_idx':None,
                            'ret_info':ret_info[ii], # ptr
                            'stage':None,'sp_info':None,'connected':0})
        pass

    # add in (kludge in??) stdin --> index mach_l_len
    #    see fo2node 'mach_idx':mach_l_len below
    g_internal_info.append( {'gbl_branch_idx':None,
                             'ret_info':None, # ret_info NOT NEEDED!
                             'stage':None,'sp_info':None,'connected':1} )
    g_num_connects = 0
    g_connects_expected = 0
    select_l = []
    fo2node_map = {}
    # if "input-to-all-branches", I want to make sure that input is excepted
    # (from stdin) and sent to _all_ branches. In order to do that, I must
    # wait to accept input until after _all_ branches are ready to be sent
    # the input. I try to guarantee this by waiting until all branches are
    # "connected".  A "connection" is established/counted when the
    # CONNECT_MAGIC cookie is received from the remote node. It is assumed
    # that at that point stdin data will be ready to be consumed.
    # If, however, the remote connection to a node or set of nodes requires
    # a passwd, the CONNECT_MAGIC will not be received until the passwd is
    # entered.  For the cases where either no stdin is needed by the
    # command or when all nodes will need the same passwd, using the --pty
    # options (indicating passwd will be needed by at least one node), the
    # waiting for all connections does not occur.
    # It really would not be recommended to rgang a cmd that requires stdin
    # to a set of nodes that also requires a passwd, in case by chance, one
    # of the nodes really does not need a passwd, in which case the passwd
    # would be sent as input to the cmd. With -pty (assuming for passwd)
    # and --input-to-all-branches is used with a large number of nodes, a
    # manual delay should be used to make sure that all connections a ready
    # for the passwd.
    if not g_opt['input-to-all-branches'] or g_opt['pty']:
        try:
            fd = sys.stdin.fileno()   # in python3, stdin in <type 'None'> when <&-
            os.fstat(fd)
            select_l.append(fd)
            fo2node_map[fd] = {'mach_idx':mach_l_len,'std':None}  # KLUDGE ALERT - stdin is "extra machine" (see "SPECIAL STDIN FLAG" below)
        except:
            # could be 'rgang node command <&-'
            # try to make an fd 0 because 0 is special and if it is
            # closed now, pipe or pty.fork will allocate it and then I'll
            # try to dup it to itself then close it -- I guess I should
            # probably check for fd==0 before dup
            fd = os.open('/dev/null', os.O_RDONLY ) # hopefully fd==0????
            pass
        need_stdin_after_connects = 0
    else:
        need_stdin_after_connects = 1

    branch_input_l = []
    g_branch_info_l = []
    g_timeout_l = []
    g_processing_idx = 0

    have_me = 0 # basicaly, flag to skip past idx 0 in branch processing below
    TRACE(5,'rgang - type(g_mach_l[0])=%s g_thisnode.is_me(%s)=%d',
          type(g_mach_l[0]), g_mach_l[0], g_thisnode.is_me(g_mach_l[0]) )
    #or g_mach_l[0] == 'localhost' 
    if not g_opt['c'] and not g_opt['serial'] and ( g_thisnode.is_me(g_mach_l[0]) or g_opt['do-local'] ):
        have_me = 1
        ret_info[0] = {'name':g_mach_l[0],'stdout':b'','stderr':b'','rmt_sh_sts':None,'crc32':0}
        g_branch_info_l.append( {'active_head':0,'branch_end_idx':1} )
        gbl_branch_idx = len(g_branch_info_l)-1     # len would be 1 here ==> gbl_branch_idx = 0
        g_internal_info[0] = {'gbl_branch_idx':gbl_branch_idx,
                            'ret_info':ret_info[0], # ptr
                            'stage':None,'sp_info':None,'connected':0}
        TRACE( 5, 'rgang local spawn_cmd do-local="%s" ("" causes rsh)', g_opt['do-local'] )
        mach_idx = 0
        sp_info = spawn_cmd( g_internal_info[mach_idx], mach_idx, opts, g_args, [g_mach_l[0]], g_opt['do-local'] )        #1 not g_opt['c'] and g_thisnode.is_me(g_mach_l[0])
        info_update( 0, fo2node_map, sp_info, select_l )
        branch_input_l.append( sp_info[1] )
        # no timeout

    overall_status = 0
    START = 0; END = 1
    # outer loops result when --serial is specified. It is processed in
    # conjunction with the --nway option to specify the number of outer loops.
    # (nway==0 means all nodes so just specifying --serial with --nway=0 gives
    # "completely serial" operation. --serial with --nway=2 with 400 nodes
    # would do 2 set of 200_parallel_spawns This can be demonstrated via:
    #   rgang.py --serial --nway=2 "192.168.1.136{,,,,,}" 'sleep 8;date'
    inner_nway_first = inner_nway  # with outer_nway (other than 1), (and 
    #                      inner_nway==0), group_len can easily change (i.e.
    #       increase by 1 (157nodes/3groups=52+53+52) and therefore the
    #       resultant inner_nway = group_len should be done again.
    for outer_group_idx in range(outer_nway):
        if g_opt['serial']=='' or g_opt['serial']=='0':
            g_grp_idxs = get_nway_indexes( outer_nway, outer_group_idx, mach_l_len, have_me)
        else:
            grp_strt=outer_group_idx*int(g_opt['serial'])
            grp_end =(outer_group_idx+1)*int(g_opt['serial'])
            if grp_end > mach_l_len: grp_end = mach_l_len
            g_grp_idxs=(grp_strt,grp_end)
            pass

        # START EACH BRANCH
        #    need to get:
        #      - list for select for get output_line and 
        #      - map of select fo to node
        group_len = g_grp_idxs[END] - g_grp_idxs[START]
        if inner_nway > group_len or inner_nway_first == 0: inner_nway = group_len

        for inner_branch_idx in range(inner_nway):
            branch_idxs = get_nway_indexes( inner_nway, inner_branch_idx, group_len)
            branch_len = branch_idxs[END] - branch_idxs[START]
            mach_idx = g_grp_idxs[START] + branch_idxs[START]
            branch_end_idx = mach_idx + branch_len
            g_branch_info_l.append( {'active_head':mach_idx,'branch_end_idx':branch_end_idx} )
            gbl_branch_idx = len(g_branch_info_l)-1
            for ii in range(branch_len):
                ret_info[mach_idx+ii] = {'name':g_mach_l[mach_idx+ii],
                                         'stdout':b'','stderr':b'','rmt_sh_sts':None,'crc32':0}
                g_internal_info[mach_idx+ii] = {'gbl_branch_idx':gbl_branch_idx,
                                              'ret_info':ret_info[mach_idx+ii], # ptr
                                              'stage':None,'sp_info':None,'connected':0}
            branch_nodes = g_mach_l[mach_idx:branch_end_idx]
            sp_info = spawn_cmd( g_internal_info[mach_idx], mach_idx, opts, g_args, branch_nodes, 0 )                     #2 for inner_branch_idx in ...
            TRACE( 6, 'rgang after initial spawn_cmd gbl_branch_idx=%d branch_len=%d sp_info=%s', gbl_branch_idx, branch_len, sp_info )
            info_update( mach_idx, fo2node_map, sp_info, select_l )
            branch_input_l.append( sp_info[1] )
            pass

        if g_opt['pypickle'] == '1':
            pypickle_report_after_time = time.time() + 3.0
            pass

        # NOW DO THE PROCESSING
        #
        if not g_opt['pyret']: header( g_mach_l[g_processing_idx], g_args, g_processing_idx )
        while g_processing_idx < g_grp_idxs[END]:

            if need_stdin_after_connects and g_num_connects == g_connects_expected:
                #time.sleep(30)
                select_l.insert(0,sys.stdin.fileno())
                fo2node_map[sys.stdin.fileno()] = {'mach_idx':mach_l_len,'std':None}
                need_stdin_after_connects = 0
                pass

            if g_timeout_l:
                # 3 cases:
                # 1) "connect" timeout period expires while waiting at select
                # 2) "connect" timeout period expires while processing for some
                #    node
                # 3) "connect" timeout period never expires as all nodes
                #    "connect" promptly
                timeout_wait = g_timeout_l[0]['timeout_expires'] - time.time()
                if timeout_wait < 0: timeout_wait = 0
                polling=0
            elif polling < 2: timeout_wait = 2.0  # general "poll" timeout -- could give a chance to send pickle?
            else:            timeout_wait = None

            if g_opt['pypickle']=='1' and polling<=2 and time.time() > pypickle_report_after_time:
                pickle_to_stdout( ret_info )
                #for ii in range(len(ret_info)):
                #    # clear buffered data
                #    ret_info[ii]['stdout']=ret_info[ii]['stderr']=b''
                #    pass
                pypickle_report_after_time = time.time() + 2.0
                #g_opt['pypickle']='0'    # debug, just do 1 here (still do at end)
                pass

            # DO THE SELECT TO (potentially) GET SOME DATA
            #        chk_exit indicate that select indicated a file, but the
            #                 read of the file returned 0 bytes (ss=b''); the
            #                 process associated with the particular file/node
            #                 probably exited.
            #                 If check_exit==1 then the following should be true:
            #                     ss==b''
            #                     fo!=None
            #                     sh_exit_stat==None
            #              ss is the output data returned unless there is a
            #                    timeout
            #              fo is the file/node to process, unless timeout
            #    sh_exit_stat is set if command exit_status (STATUS_MAGIC) was
            #                 received/indicated.
            # When a timeout occurs, the return values will be (as initialize
            # in get_output):
            #     chk_exit=0;ss=b'';fo=None;sh_exit_stat=None
            TRACE( 7, 'rgang before get_output wait=%s select_l=%s need_stdin=%d g_num_connects=%d',
                   timeout_wait, select_l, need_stdin_after_connects, g_num_connects )
            chk_exit,ss,fo,mach_idx,sh_exit_stat = get_output( select_l, fo2node_map, timeout_wait )
            TRACE( 7, 'rgang after  get_output chk_exit=%s len(ss)=%d fo=%s mach_idx=%s sh_exit_stat=%s type(ss)=%s',
                   chk_exit,len(ss),fo,mach_idx,sh_exit_stat,type(ss) )

            if fo == None:
                # timeout
                # should be able to do the processing here and not continue, but return
                # chk_exit=1 and mach_idx

                #move processing from above and do it here to properly continue and finish processing after killing process
                # DO CONNECT TIMEOUT PROCESSING NOW
                # IN THE CASE of an rgang node timing out, A NEW TIMEOUT
                # PERIOD WOULD BE INITIATED
                # WHAT HAPPENS IF IT CHANGES THE processing _idx???
                if g_timeout_l:
                    mach_idx = timeout_connect_process()
                    chk_exit,ss,sh_exit_stat = 1,b'',None
                    polling=0
                else: polling+=1; continue  # must be general "pool" timeout -- loop back around
            else:
                # no timeout
                polling=0
                if mach_idx == mach_l_len:  # SPECIAL STDIN FLAG
                    TRACE( 8, 'rgang stdin g_processing_idx=%d', g_processing_idx )
                    if len(ss):
                        #stdin_bytes = stdin_bytes + len(ss)
                        if g_opt['input-to-all-branches'] or g_opt['pyret'] :
                            #TRACE( 9, "rgang branch_input_l=%s", branch_input_l )
                            for br_sdtin in branch_input_l:
                                bytes_written = os.write( br_sdtin, ss )
                                while bytes_written < len(ss):
                                    bytes_this_write = os.write( br_sdtin, ss[bytes_written:] )
                                    bytes_written = bytes_written + bytes_this_write
                        else:
                            os.write( g_internal_info[g_processing_idx]['sp_info'][1], ss )
                    else:
                        info_clear( sys.stdin.fileno(), fo2node_map, select_l )

                        # BUT WHAT ABOUT "rgang nodes 'echo hi' <&-"

                        #TRACE( 9, "rgang closing everyone's stdin after %d bytes l=%s", stdin_bytes, branch_input_l )
                        TRACE( 9, "rgang closing everyone's stdin" )
                        for br_stdin in branch_input_l:
                            os.close( br_stdin )
                            # mi = fo2node_map[br_stdin]['mach_idx']
                            del( fo2node_map[br_stdin] )
                            # if g_opt['mach_idx_offset']!='':  # "initiator" node check
                            #     # not initiator node
                            #     pid = g_internal_info[mi]['sp_info'][0]
                            #     os.kill(pid,1)
                            #     rpid,unused_sts = wait_nohang( pid )
                            #     if rpid == pid: continue
                            #     os.kill(pid,13)
                            #     rpid,unused_sts = wait_nohang( pid )
                            #     pass
                            pass
                        # this should cause (via chain reaction) the remote
                        # cmd's to exit; the branch_input_l will be cleaned
                        # up when they do; as our stdin is no longer in the
                        # select_l, this whole "SPECIAL STDIN" code should
                        # not get executed again.
                        pass
                    continue  # after STDIN PROCESSING

                # PROCESS THE DATA
                if fo2node_map[fo]['std'] == sys.stdout.fileno() and \
                   g_internal_info[mach_idx]['stage'] == 'rgang':
                    ss = do_stage_rgang_processing( ss, mach_idx, ret_info )
                if do_output( mach_idx, g_processing_idx, ret_info ):
                    TRACE( 8, 'rgang: PROCESS THE DATA - do_output(mach_idx=%d...) returned true',mach_idx )
                    os.write( fo2node_map[fo]['std'], ss )    # could be stderr or stdout
                elif fo2node_map[fo]['std'] == sys.stdout.fileno():
                    ret_info[mach_idx]['stdout'] += ss
                else: ret_info[mach_idx]['stderr'] = ret_info[mach_idx]['stderr'] + ss
                if g_opt['ditto']: ret_info[mach_idx]['crc32'] = zlib.crc32(ss,ret_info[mach_idx]['crc32'])
                pass

            if sh_exit_stat != None:
                # The STATUS_MAGIC should be the last thing that comes out on
                # stdout.  There may be some stderr output next (or shortly).
                # A problem can occur where stderr will be lost if
                # this mach_idx==g_processing_idx+1 and "ACTIVE OUTPUT PROCESSING"
                # below passes by this mach_idx (at the end of the next
                # DO THE PROCESSING loop). The easiest thing to do (without
                # worrying about rgang stage) is to just give the system time
                # to see if the stderr fd will get data. Note, it would be nice
                # if I could get the sh_exit_stat on the higher number fd
                # (stderr) but I know of no simple way to do that. If I
                # could, I would better be asured that all stdout and
                # stderr has been processed.
                if not chk_exit:
                    chk_exit = get_stderr_output( ret_info, fo2node_map,
                                                  mach_idx, g_processing_idx,
                                                  tmo=.5 )
                    TRACE( 8, 'sh_exit_stat w/o chk_exit -- now chk_exit=%d', chk_exit )
                    pass
                ret_info[mach_idx]['rmt_sh_sts'] = sh_exit_stat # OK if we overwrite timeout kill status
                pass


            TRACE( 8, 'CHECK FOR BRANCH/GROUP STATUS mach_idx=%d chk_exit=%d g_processing_idx=%d crc32=0x%08x'\
                       %(mach_idx,chk_exit,g_processing_idx,ret_info[mach_idx]['crc32']) )
            #
            if chk_exit:

                TRACE( 8, 'rgang chk_exit mach_idx=%d g_processing_idx=%d sp_info=%s',
                       mach_idx, g_processing_idx, g_internal_info[mach_idx]['sp_info'] )

                # cleanup_output_status
                # if the fd that trigger us was stdOUT, then we need to check stdERR
                pid = g_internal_info[mach_idx]['sp_info'][0]
                if g_internal_info[mach_idx]['sp_info'][3] \
                   and ( ( fo != None and fo2node_map[fo]['std'] == sys.stdout.fileno() ) \
                         or fo == None ):
                    TRACE( 2, 'rgang CHECKing stdERR fo=%s pid=%d mach_idx=%d', fo, pid, mach_idx )
                    #get_stderr_output( ret_info, fo2node_map, mach_idx, g_processing_idx )
                    chk = 0; fo2 = g_internal_info[mach_idx]['sp_info'][3] # init this as fo may be None (i.e. tmo)
                    while not chk and fo2 != None:
                        chk,ss,fo2,mi,dont_used = get_output( [g_internal_info[mach_idx]['sp_info'][3]], # 3 is stdERR
                                                              fo2node_map, 0 )
                        ret_info[mach_idx]['stderr'] = ret_info[mach_idx]['stderr'] + ss
                        if g_opt['ditto']: ret_info[mach_idx]['crc32'] = zlib.crc32(ss,ret_info[mach_idx]['crc32'])
                        pass


                # if the fd that trigger us was stdERR, then we need to check stdOUT
                if g_internal_info[mach_idx]['sp_info'][2] \
                   and ( ( fo != None and fo2node_map[fo]['std'] == sys.stderr.fileno() ) \
                         or fo == None ):
                    TRACE( 2, 'rgang CHECKing stdOUT fo=%s pid=%d mach_idx=%d', fo, pid, mach_idx )
                    # There quite possibly could be 2 iteration through
                    # this while. If the main get_output (above) had stderr
                    # in the select list first AND the shell is really fast AND
                    # there is little to no output, then the CONNECT machanism
                    # may not have happened and then the 1st loop here will
                    # cause the a '' value to be returned for ss; chk will be 0
                    # however.
                    chk = 0; fo2 = g_internal_info[mach_idx]['sp_info'][2] # init this as fo may be None (i.e. tmo)
                    while not chk and fo2 != None:
                        chk,ss,fo2,mi,sh_exit_stat = get_output( [g_internal_info[mach_idx]['sp_info'][2]],  # 2 is stdout
                                                                fo2node_map, 0 )
                        TRACE( 7, 'after "stderr-chk-stdout" get_output len(ss)=%d', len(ss) )
                        if g_internal_info[mach_idx]['stage'] == 'rgang':
                            ss = do_stage_rgang_processing( ss, mach_idx, ret_info )
                        if sh_exit_stat != None:
                            ret_info[mach_idx]['rmt_sh_sts'] = sh_exit_stat # OK if we overwrite timeout kill status
                            pass
                        ret_info[mach_idx]['stdout'] = ret_info[mach_idx]['stdout'] + ss
                        if g_opt['ditto']: ret_info[mach_idx]['crc32'] = zlib.crc32(ss,ret_info[mach_idx]['crc32'])
                        pass
                    pass

                # DONE COLLECTING OUTPUT from process; write-n-clear any buffered output
                if do_output( mach_idx, g_processing_idx, ret_info ):
                    TRACE( 8, 'print any previously store stdout/err mach_idx=%d crc=0x%08x', mach_idx, ret_info[mach_idx]['crc32'] )
                    if g_opt['ditto'] and g_opt['mach_idx_offset']=='' and mach_idx!=0:
                        if ret_info[g_processing_idx]['crc32'] == ret_info[g_processing_idx-1]['crc32']:
                            os.write( sys.stdout.fileno(),b'ditto\n')
                        else:
                            os.write( sys.stdout.fileno(), ret_info[mach_idx]['stdout'] )
                            os.write( sys.stderr.fileno(), ret_info[mach_idx]['stderr'] )
                    else:
                        os.write( sys.stdout.fileno(), ret_info[mach_idx]['stdout'] )
                        os.write( sys.stderr.fileno(), ret_info[mach_idx]['stderr'] )
                    ret_info[mach_idx]['stdout']=b''
                    ret_info[mach_idx]['stderr']=b''
                    pass


                # remove sub-process's output and input fds from
                # the select list, fo2node_map, branch_input_l
                for ffo in g_internal_info[mach_idx]['sp_info'][2:]:
                    if ffo: info_clear( ffo, fo2node_map, select_l )  # does os.close()
                branch_input_l.remove( g_internal_info[mach_idx]['sp_info'][1] )
                if g_internal_info[mach_idx]['sp_info'][1] in fo2node_map.keys():
                    del( fo2node_map[g_internal_info[mach_idx]['sp_info'][1]] )
                    try:
                        os.close(g_internal_info[mach_idx]['sp_info'][1])
                        #os.write(sys.stderr.fileno(),"closed ['sp_info'][1]=%d\n"%(g_internal_info[mach_idx]['sp_info'][1],))
                    except:
                        TRACE( 2, "os.close(g_internal_info[mach_idx=%d]['sp_info'][1]=%d)",
                               mach_idx, g_internal_info[mach_idx]['sp_info'][1] )
                        raise

                gbl_branch_idx = g_internal_info[mach_idx]['gbl_branch_idx']
                timeout_cancel( gbl_branch_idx )

                try:
                    opid,status = os.waitpid( pid, 0 )
                    if opid != pid: raise ProgramError('process did not exit')
                    TRACE( 2, 'rgang waitpid got status for pid=%d mach_idx=%d gbl_branch_idx=%d status=%s overall=%s',
                           pid, mach_idx, gbl_branch_idx, status, overall_status )
                    status = (status>>8)
                except:       # i.e. (OSError, '[Errno 10] No child processes')
                    # must have been killed in timeout_connect_process
                    exc, value, tb = sys.exc_info()
                    #ff=os.popen('pstree -p'); ll_a=ff.readlines(); ff.close(); TRACE( 10, "pstree -p\n%s", ''.join(ll_a) )
                    p2,s2 = wait_nohang( pid )
                    TRACE( 10, 'except - chk_exit waitpid(pid=%d) s2=%s - %s: %s'%(pid,s2,exc,value) )
                    status = g_internal_info[mach_idx]['ret_info']['rmt_sh_sts']
                    TRACE( 2, 'rgang waitpid NO status for pid=%d mach_idx=%d gbl_branch_idx=%d using status=%s overall=%s',
                           pid, mach_idx, gbl_branch_idx, status, overall_status )
                    pass


                # g_internal_info[x].keys() = ('stage','connected','sp_info','gbl_branch_idx','ret_info')
                # g_internal_info[x]['ret_info'].keys() = ('name','stdout','stderr','rmt_sh_sts')

                if g_internal_info[mach_idx]['stage'] == 'rgang':
                    g_internal_info[mach_idx]['stage'] = 'done'  # SEE "ACTIVE OUTPUT PROCESSING" BELOW
                    # EEEEEEEE THIS HAS RCP OUTPUT AND RGANG RET!
                    # BUT WAIT, NORMALLY THERE IS NO RCP STDOUT (maybe stderr
                    #stdout should be in form: llllllll:pickle
                    set_connected_g( mach_idx, 0 ) # if it's not connected now, it never will be

                    branch_idx = g_internal_info[mach_idx]['gbl_branch_idx']
                    branch_mach_head = g_branch_info_l[branch_idx]['active_head']
                    branch_mach_end  = g_branch_info_l[branch_idx]['branch_end_idx']
                    branch_len = branch_mach_end - branch_mach_head

                    if g_opt['c']: offset = 1
                    else:          offset = 0

                    if ret_info[mach_idx]['rmt_sh_sts'] != None:
                        for ii in range(branch_len-offset):
                            TRACE( 5,
                                   'mach_idx=%d ii=%d branch_len=%d offset=%d len(ret_info)=%d rmt_sh_sts=%s',
                                   mach_idx,ii,branch_len,offset,len(ret_info),
                                   ret_info[mach_idx+offset+ii]['rmt_sh_sts'] )
                            if ret_info[mach_idx+offset+ii]['rmt_sh_sts'] == None:
                                ret_info[mach_idx+offset+ii]['rmt_sh_sts'] = 3
                                pass
                            overall_status = overall_status | ret_info[mach_idx+offset+ii]['rmt_sh_sts']
                            pass
                        pass
                    else:
                        # something bad happened
                        if g_opt['c']:
                            ret_info[mach_idx]['stderr'] = ret_info[mach_idx]['stderr'] + '%s: warning: "rcp" %s failed\n'%(APP,APP)
                        else:
                            if ret_info[mach_idx]['rmt_sh_sts'] == None:
                                ret_info[mach_idx]['rmt_sh_sts'] = 2
                                TRACE( 12, 'rgang #1 rmt_sh_sts=2' ) # rsh failure or shell abort (i.e. syntax error)
                                pass
                            ret_info[mach_idx]['rmt_sh_sts'] = ret_info[mach_idx]['rmt_sh_sts'] | status
                            overall_status = overall_status | ret_info[mach_idx]['rmt_sh_sts']
                            pass
                        gbl_branch_idx = g_internal_info[mach_idx]['gbl_branch_idx']
                        branch_end_idx = g_branch_info_l[gbl_branch_idx]['branch_end_idx']
                        branch_nodes = g_mach_l[mach_idx+1:branch_end_idx]
                        if branch_nodes:
                            # I MAY ONLY WANT TO DO THIS IF not connected???
                            TRACE( 13, 'rgang spawn_cmd branch_node is %s', branch_nodes )
                            g_branch_info_l[gbl_branch_idx]['active_head'] = mach_idx+1
                            #timeout_cancel( gbl_branch_idx ) # cancel 1st timeout for this gbl_branch_idx
                            sp_info = spawn_cmd( g_internal_info[mach_idx+1], mach_idx+1, opts, g_args, branch_nodes, 0 ) #3 after bad rgang
                            info_update( mach_idx+1, fo2node_map, sp_info, select_l )
                            branch_input_l.append( sp_info[1] )
                            pass
                        pass

                    if do_output( mach_idx, g_processing_idx, ret_info ):
                        TRACE( 8, 'stage==rgang write-n-clear stdout/err mach_idx=%d crc=0x%08x', mach_idx, ret_info[mach_idx]['crc32'] )
                        if g_opt['ditto'] and g_opt['mach_idx_offset']=='' and mach_idx!=0:
                            if ret_info[g_processing_idx]['crc32'] == ret_info[g_processing_idx-1]['crc32']:
                                os.write( sys.stdout.fileno(),b'ditto\n')
                            else:
                                os.write( sys.stdout.fileno(), ret_info[g_processing_idx]['stdout'])
                                os.write( sys.stderr.fileno(), ret_info[g_processing_idx]['stderr'])
                        else:
                            os.write( sys.stdout.fileno(), ret_info[g_processing_idx]['stdout'])
                            os.write( sys.stderr.fileno(), ret_info[g_processing_idx]['stderr'])
                        ret_info[g_processing_idx]['stdout']=b''
                        ret_info[g_processing_idx]['stderr']=b''
                        pass
                    pass

                elif g_internal_info[mach_idx]['stage'] == 'rcp':
                    # STRIP OFF NODE HERE
                    if ret_info[mach_idx]['rmt_sh_sts'] != None: sys.stderr.write('1EEEEEEEEEE\n')
                    ret_info[mach_idx]['rmt_sh_sts'] = status
                    overall_status = overall_status | ret_info[mach_idx]['rmt_sh_sts']
                    gbl_branch_idx = g_internal_info[mach_idx]['gbl_branch_idx']
                    branch_end_idx = g_branch_info_l[gbl_branch_idx]['branch_end_idx']
                    branch_nodes = g_mach_l[mach_idx+1:branch_end_idx]
                    if status == 0 and branch_nodes:
                        TRACE( 14, 'rgang rcp spawn_cmd branch_nodes is %s', branch_nodes )
                        #timeout_cancel( gbl_branch_idx )
                        sp_info = spawn_cmd( g_internal_info[mach_idx], mach_idx, opts, g_args, branch_nodes, 0 )         #4 the rgang after good rcp
                        info_update( mach_idx, fo2node_map, sp_info, select_l )
                        branch_input_l.append( sp_info[1] )
                        g_branch_info_l[gbl_branch_idx]['active_head'] = mach_idx
                    elif status != 0 and branch_nodes:
                        # start rcp stage on next node
                        TRACE( 15, 'rgang rcp spawn_cmd branch_nodes is %s', branch_nodes )
                        #timeout_cancel( gbl_branch_idx )
                        sp_info = spawn_cmd( g_internal_info[mach_idx+1], mach_idx+1, opts, g_args, branch_nodes, 0 )     #5 bad rcp, next node rcp
                        info_update( mach_idx+1, fo2node_map, sp_info, select_l )
                        branch_input_l.append( sp_info[1] )
                        g_branch_info_l[gbl_branch_idx]['active_head'] = mach_idx+1
                    else:
                        # DONE WITH BRANCH
                        pass
                    pass

                elif g_internal_info[mach_idx]['stage'] == 'rsh':  # no further branch processing
                    set_connected_g( mach_idx, 0 ) # if it's not connected now, it never will be
                    if ret_info[mach_idx]['rmt_sh_sts'] == None:
                        ret_info[mach_idx]['rmt_sh_sts'] = 4
                        TRACE( 16, 'rgang #2 rmt_sh_sts=4' ) # shell abort (i.e. syntax error)
                    try: ret_info[mach_idx]['rmt_sh_sts'] = ret_info[mach_idx]['rmt_sh_sts'] | status
                    except TypeError:
                        TRACE( 2, "ret_info[mach_idx]['rmt_sh_sts']=%s status=%s", ret_info[mach_idx]['rmt_sh_sts'], status)
                        raise
                    overall_status = overall_status | ret_info[mach_idx]['rmt_sh_sts']

                else:  # local - no further branch processing
                    if ret_info[mach_idx]['rmt_sh_sts'] != None: sys.stderr.write('4EEEEEEEEEE\n')
                    ret_info[mach_idx]['rmt_sh_sts'] = status
                    try: overall_status = overall_status | ret_info[mach_idx]['rmt_sh_sts']
                    except TypeError:
                        TRACE( 2, "overall_status=%s ret_info[mach_idx]['rmt_sh_sts']=%s", overall_status, ret_info[mach_idx]['rmt_sh_sts'] )
                        raise


                # ACTIVE OUTPUT PROCESSING
                if mach_idx == g_processing_idx:
                    if g_internal_info[g_processing_idx]['stage'] == 'rgang': continue # wait for ['stage'] = 'done' (above)
                    TRACE( 28, 'rgang calling initiator_node_status at ACTIVE OUTPUT PROCESSING #1 mach_idx=%d', mach_idx )
                    initiator_node_status( mach_idx )                    
                    g_processing_idx = g_processing_idx + 1
                    ##while g_processing_idx < (g_grp_idxs[END]-1):
                    while g_processing_idx < g_grp_idxs[END]:
                        ##g_processing_idx = g_processing_idx + 1
                        TRACE( 8,
                               "g_processing_idx=%d stage=%s rmt_sh_sts=%s len(stdout)=%d len(stderr)=%d crc32=0x%08x crc-132=0x%08x",
                               g_processing_idx,
                               g_internal_info[g_processing_idx]['stage'],
                               ret_info[g_processing_idx]['rmt_sh_sts'],
                               len(ret_info[g_processing_idx]['stdout']),
                               len(ret_info[g_processing_idx]['stderr']),
                               ret_info[g_processing_idx]['crc32'],
                               ret_info[g_processing_idx-1]['crc32'] )
                        if not g_opt['pyret']: header( g_mach_l[g_processing_idx], g_args, g_processing_idx )
                        if g_internal_info[g_processing_idx]['stage'] == 'rgang': break # wait for ['stage'] = 'done' (above)
                        TRACE( 28, 'rgang calling initiator_node_status at ACTIVE OUTPUT PROCESSING #2 mach_idx=%d', mach_idx )
                        initiator_node_status( g_processing_idx )                    
                        if ret_info[g_processing_idx]['rmt_sh_sts'] == None:
                            # This is the _not_ normal case
                            if not g_opt['pyret']:
                                if g_opt['ditto'] and g_opt['mach_idx_offset']=='': break # do not "print-n-...clear"
                                TRACE( 8, 'print-n-flush and clear stdout/err idx=%d', g_processing_idx )
                                os.write( sys.stdout.fileno(),ret_info[g_processing_idx]['stdout'])
                                os.write( sys.stderr.fileno(),ret_info[g_processing_idx]['stderr'])
                                ret_info[g_processing_idx]['stdout'] = b''
                                ret_info[g_processing_idx]['stderr'] = b''
                                pass
                            break
                        if not g_opt['pyret']:
                            if g_opt['ditto'] and g_opt['mach_idx_offset']=='': # g_processing_idx should never be 0
                                if ret_info[g_processing_idx]['crc32'] == ret_info[g_processing_idx-1]['crc32']:
                                    os.write( sys.stdout.fileno(),b'ditto\n')
                                else:
                                    os.write( sys.stdout.fileno(),ret_info[g_processing_idx]['stdout'])
                                    os.write( sys.stderr.fileno(),ret_info[g_processing_idx]['stderr'])
                            else:
                                os.write( sys.stdout.fileno(),ret_info[g_processing_idx]['stdout'])
                                os.write( sys.stderr.fileno(),ret_info[g_processing_idx]['stderr'])
                                pass
                            ret_info[g_processing_idx]['stdout'] = b''
                            ret_info[g_processing_idx]['stderr'] = b''
                            pass
                        g_processing_idx = g_processing_idx + 1
                        pass
                    pass
                pass # end of "if chk_exit" processing

            pass # while g_processing_idx < g_grp_idxs[END]:

    if g_opt['pty']: clean()
    if not g_opt['pyret'] and g_opt['n']=='2': sys.stdout.write( '\n' )
    if   g_opt['pyprint']:  pprint.pprint( ret_info )
    elif g_opt['pypickle']: pickle_to_stdout( ret_info )
    return overall_status,ret_info
    # rgang


###############################################################################
# import sys,os,time
g_prop=0
g_propeller=(b'|',b'/',b'-',b'\\',b'|',b'/',b'-',b'\\')
g_prop_t=time.time()+2.0
def prop():
    global g_prop, g_prop_t
    if g_opt.get('mach_idx_offset',''): return None # only write to stderr/out after exception on "initiator" node
    if time.time() > g_prop_t:
        os.write( sys.stderr.fileno(), g_propeller[g_prop]+b'\b' )
        g_prop=(g_prop+1)%len(g_propeller)
        g_prop_t=time.time()+1.0
        pass
    return None

def keyboard_sig_handler(signum=None,frame=None):
    # "stty -a"   shows:                               intr    quit    susp
    # "man stty" appear to align these with:          SIGINT  SIGQUIT SIGTSTP
    # these are normally (currently) associated with:  ^C       ^\     ^Z
    stdout_chars = stderr_chars = completed = completed_ok = completed_err = incomplete = 0
    real_machines=len(g_internal_info)-1  # see fo2node 'mach_idx':mach_l_len above
    for mach_idx in range(real_machines):
        if type(g_internal_info[mach_idx])==type({}):
            if g_internal_info[mach_idx]['ret_info'] != None:
                stdout_chars += len(g_internal_info[mach_idx]['ret_info']['stdout'])
                stderr_chars += len(g_internal_info[mach_idx]['ret_info']['stderr'])
                if g_internal_info[mach_idx]['ret_info']['rmt_sh_sts'] != None:
                    completed+=1
                    if g_internal_info[mach_idx]['ret_info']['rmt_sh_sts'] == 0: completed_ok+=1
                    else:                                                        completed_err+=1
                else: incomplete+=1
                pass
            else: incomplete+=1
        else: incomplete+=1
        pass
    ostr='nodes=%-4s stOB=%-6s stEB=%-6s inc=%-4s ok=%-4s err=%-4s conn=%-3s expt=%-3s'%\
          (real_machines,stdout_chars,stderr_chars,incomplete,completed_ok,completed_err,
           g_num_connects,g_connects_expected)
    #sys.stderr.write(ostr+'\b'*len(ostr));sys.stderr.flush()
    sys.stderr.write('\r'+ostr+'\n');sys.stderr.flush()
    return None

def main():
    import sys                          # argv, exit
    import select                       # select
    import socket                       # gaierror
    global g_processing_idx
    prv_hand = signal.signal(signal.SIGQUIT,keyboard_sig_handler)
    if 1:                               # switch to 0 to debug
        try: total_stat,ret_list = rgang( sys.argv[1:] ) # <--<<< RGANG command
        #except KeyboardInterrupt, detail:
        #except KeyboardInterrupt or SystemExit, detail:
        except:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            exc, value, tb = sys.exc_info()
            if exc == SystemExit: pass #; sys.stdout.write('Yes, SystemExit\n')
            if g_opt['tlvlmsk']:
                for ln in traceback.format_exception( exc, value, tb ):
                    sys.stderr.write(ln)
                    pass
                pass
            TRACE( 10, 'except - main - rgang %s', exc )
            prop()
            pids = kills = 0; pids_l=[]
            total_stat=0
            for mach_idx in range(len(g_internal_info)):
                # There is a case, for example: rgang <node> 'sleep 5 &'
                # where rgang will receive the "remote shell status", but because
                # stdout/err were not closed (i.e.:rgang <node> 'sleep 5 >&- 2>&- &' ), the
                # remote shell will hang until the backgrounded process completes.
                # In this case I will have a 'rmt_sh_sts' (it will NOT == None);
                # so I should NOT do 'rmt_sh_sts' checking.
                #if g_internal_info[mach_idx]['ret_info'] != None \
                #   and g_internal_info[mach_idx]['ret_info']['rmt_sh_sts'] == None \
                #   and g_internal_info[mach_idx]['sp_info'] != None:
                prop()
                if type(g_internal_info[mach_idx])==type({}) and g_internal_info[mach_idx]['sp_info'] != None:
                    if g_internal_info[mach_idx]['ret_info'] != None and \
                       g_internal_info[mach_idx]['ret_info']['rmt_sh_sts'] != None:
                        total_stat |= g_internal_info[mach_idx]['ret_info']['rmt_sh_sts']
                        pass
                    # close stdin and give it a chance to ripple through the rgang
                    #if g_internal_info[mach_idx]['sp_info'][1] in fo2node_map.keys(): # global name 'fo2node_map' is not defined
                    try:  # Note: use try/except to avoid "OSError: [Errno 9] Bad file descriptor" AS fo2node_map prevents using 'if' above
                        sp_stdin = g_internal_info[mach_idx]['sp_info'][1]
                        os.close( sp_stdin ); select_interrupt([],[],[],0.05)     # use select to sleep sub second
                    except:
                        #os.write( sys.stderr.fileno(), 'why is %d a Bad file descriptor\n'%(sp_stdin,) )
                        pass
                    pid = g_internal_info[mach_idx]['sp_info'][0]
                    pids+=1
                    # do kill and kill check here
                    for sig in (1,2,15,0):  # 1=HUP, 2=INT(i.e.^C), 15=TERM(default "kill"), 3=QUIT(i.e.^\), 9=KILL
                        prop()
                        rpid,unused_sts = wait_nohang( pid )
                        if rpid == -1: break
                        if rpid == pid:  # OK, process is out-of-there
                            TRACE( 30, "main wait_nohang(pid=%d) exited", pid )
                            pids_l.append(pid)
                            if g_internal_info[mach_idx]['ret_info']['rmt_sh_sts'] == None:
                                g_internal_info[mach_idx]['ret_info']['rmt_sh_sts'] = 0x10
                                pass
                            break
                        os.kill(pid,sig)
                        if sig==1: kills += 1
                        prop()
                        TRACE( 30, "main os.kill(%d,%d)", pid, sig )
                        #time.sleep(1.0)
                        select_interrupt([],[],[],0.05)     # use select to sleep sub second
                        pass
                    pass
                pass
            prop()
            TRACE( 30, "main output if initiator node" )
            if exc == KeyboardInterrupt and g_opt.get('mach_idx_offset','')=='':  # "initiator" node
                #os.write(sys.stderr.fileno(),b'\npids=%d sigs_sent=%d exited=%s\n'%(pids,kills,pids_l))
                os.write(sys.stderr.fileno(),b'\nsub_processes=%d sigs_sent=%d exited=%d\n'%(pids,kills,len(pids_l)))
                mach_idx = g_processing_idx
                TRACE( 28, 'status main exception initiator_node_status loop at mach_idx=%d',mach_idx )
                while mach_idx < len(g_mach_l):
                    if type(g_internal_info[mach_idx]) == type({}): # fast ^C check
                        prop()
                        initiator_node_status( mach_idx )  # handles err-file
                        pass
                    mach_idx += 1
                    pass
                signal.signal(signal.SIGINT, signal.SIG_DFL)

                try:
                    second_ctrl_c_time=3
                    sys.stderr.write('\nanother ^C to stop output in %d'%(second_ctrl_c_time,))
                    sys.stderr.flush()
                    if second_ctrl_c_time > 0:
                        for dd in range(second_ctrl_c_time-1,-1,-1):
                            time.sleep(1)
                            sys.stderr.write('\b%d'%(dd,));sys.stderr.flush()
                            pass
                        pass
                    sys.stderr.write('\n');sys.stderr.flush()
                    # LIKE "ACTIVE OUTPUT PROCESSING" (above, at end of rgang processing loop)
                
                    if type(g_internal_info[g_processing_idx]) == type({}): # fast ^C check
                        if not g_opt.get('pyret',''):
                            # print-n-flush and clear stdout/err
                            ret_info = g_internal_info[g_processing_idx]['ret_info']
                            os.write( sys.stdout.fileno(),ret_info['stdout'])
                            os.write( sys.stderr.fileno(),ret_info['stderr'])
                            ret_info['stdout'] = b''
                            ret_info['stderr'] = b''
                            pass
                        pass
                    g_processing_idx = g_processing_idx + 1
                    while g_processing_idx < g_grp_idxs[1]:
                        if type(g_internal_info[g_processing_idx]) == type({}): # fast ^C check
                            if not g_opt.get('pyret',''):
                                ret_info = g_internal_info[g_processing_idx]['ret_info']
                                header( g_mach_l[g_processing_idx], g_args, g_processing_idx )
                                # print-n-flush and clear stdout/err
                                os.write( sys.stdout.fileno(),ret_info['stdout'])
                                os.write( sys.stderr.fileno(),ret_info['stderr'])
                                ret_info['stdout'] = b''
                                ret_info['stderr'] = b''
                                pass
                            pass
                        g_processing_idx = g_processing_idx + 1
                        pass
                    if g_opt['pty']: clean()
                    if not g_opt['pyret'] and g_opt['n']=='2': sys.stdout.write('\n')
                    if   g_opt['pyprint']:  pprint.pprint( g_ret_info )
                    elif g_opt['pypickle']: pickle_to_stdout( g_ret_info )
                    pass
                except KeyboardInterrupt: pass

                sys.stderr.write('\n')
                # emulate the old shell version of rgang when (rsh is) "interrupted"
                TRACE( 30, "main exit (1<<7)+2" )
                sys.exit( (1<<7)+2 )
                pass
            elif exc==socket.gaierror:
                sys.stderr.write('Exception -- possible name services error\n')
                #for ln in traceback.format_exception( exc, value, tb ):
                #    sys.stderr.write(ln)
                #    pass
                #pass
            pass
        #if g_opt['mach_idx_offset']=='': keyboard_sig_handler(); sys.stderr.write('\n')  # only on "initiator node"
        pass
    else: total_stat,ret_list = rgang( sys.argv[1:] )

    sys.exit( total_stat )
    # main


# this simple "if ...main..." allows for taking advantage of *experimenting
# with* the optimization (or even just the plain) byte compiled file via:
#    python -OO -c 'import rgang;rgang.main()' -nn all 'echo hi'
# and/or a small script:
#    #!/bin/sh
#    exec python -OO -c "
#    import sys;sys.argv[0]='`basename $0`';import rgang;rgang.main()" "$@"
if __name__ == "__main__": main()
