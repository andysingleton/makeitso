import argparse
import pwd
import os
import syslog
import yaml
import paramiko
import socket
import hashlib
import sys
import psutil
import pwd

class logunit ():
   """
   A class for all output from makeitso
   It allows you to be more or less verbose
   and provides the option to specify an alternate logfile
   """

   def __init__(self, quiet=False, verbose=False, logfile='syslog'):
     self.quiet = quiet
     self.verbose = verbose
     self.logfile = logfile
     self.process = sys.argv[0]

   def log(self, level='info', message='null message'):
     to_syslog = False
     to_console = False

     if level =='crit':
       loglevel = syslog.LOG_ERR
       to_syslog = True
       to_console = True
     if level == 'warn':
       to_syslog = True
       to_console = True
       loglevel = syslog.LOG_WARNING
     if level == 'info':
       to_console = True
       loglevel = syslog.LOG_INFO
     if level == 'debug':
       loglevel = syslog.LOG_DEBUG

     # Print to logfile?
     if self.verbose == True:
       to_syslog = True
       to_console = True

     if self.quiet == True:
       to_syslog = False
       to_console = False


     if to_syslog == True:
       syslog.syslog(loglevel, message)

     if to_console == True:
       print "%s: %s" % (level.upper(), message)
      
     if level == 'crit':
       exit(1)

def authorize(mislog, sig_valid, run_local, user_valid):
  # Allow execution for the following criteria:

  mislog.log('info','Checking authorization')
  mislog.log('debug',('sig match?: %s' % sig_valid))
  mislog.log('debug',('user match?: %s' % user_valid))
  mislog.log('debug',('local run?: %s' % run_local))

  # The checksum matches and the user is valid
  if sig_valid == True and user_valid == True:
    return True

  # No checksum was provided (nohashcheck), but
  # - the utility was executed locally
  # - the user is valid
  if sig_valid == False and user_valid == True and run_local == True:
    return True

  mislog.log('crit','You are not authorised to execute this action')
  return False

def execute_action(mislog, task):
  jobuser = task['user']
  jobs = task['command']
  servers = task['servers']
  cwd = task['cwd']
  failcontinue = task['failcontinue']

  for server in servers:
    mislog.log('info', 'Connecting to: '+server)
    try:
      addr = socket.gethostbyname(server)
    except:
      mislog.log('crit','DNS lookup failure for %s' % server)
    try:
      ssh = paramiko.SSHClient()
      ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
      ssh.connect(addr,username='makeitso')
    except:
      mislog.log('crit','Could not connect to %s' % server)
    try:
      channel = ssh.invoke_shell()
      channel.set_combine_stderr(True)
      stdin = channel.makefile('wb')
      stdout = channel.makefile('rb')
    except:
      mislog.log('critical','Could not run remote command on '+server)
    for comm in task['command']:
      command="sudo su - %s\n" % jobuser
      command+="cd %s\n" % cwd
      command+=comm
      command+="\n exit\n exit\n"
      mislog.log('debug', 'Executing: '+command)
      try:
        stdin.write(command)
        outstring=stdout.read()
        mislog.log('debug', 'Console output: '+outstring)
      except:
        if failcontinue == False:
          stdout.close()
          stdin.close()
          ssh.close
          mislog.log('critical',('Server %s could not finish: %s' % ( server, comm)))
        else:
          mislog.log('warn',('Server %s could not finish: %s' % ( server, comm)))
    stdout.close()
    stdin.close()
    ssh.close
  return

def get_local():
  parentpid = psutil.Process().ppid()
  grandparentpid = psutil.Process(parentpid).ppid()
  req_exe = psutil.Process(grandparentpid).name()
  if req_exe == 'makeitso':
    return True
  else:
    return False

def get_user(mislog, action_yaml):
  parentpid = psutil.Process().ppid()
  grandparentpid = psutil.Process(parentpid).ppid()
  req_user = psutil.Process(grandparentpid).username()
  for user in action_yaml['allowed']:
    if user == req_user:
      return True
  return False

### get_yaml: iterate over all yaml files ###
def get_yaml(mislog, filespec):

  yaml_object = {}
  yaml_file = open(filespec)

  try:
    yaml_object.update(yaml.load(yaml_file))
  except:
    mislog.log('crit','Could not load the yaml file. Please check syntax.')
    return False

  yaml_file.close()

  return yaml_object

### Get the signature of the file provided
def compare_sig(mislog, filespec, hashcheck):
  myfile = open(filespec)
  sig = hashlib.sha256(myfile.read()).digest()
  myfile.close()
  if sig == hashcheck:
    return True
  else:
    return False

### get_action: Extract the relevant action portion of the yaml
def get_action(mislog,env_yaml,action):
  try:
    action_yaml = env_yaml['makeitso'].action
  except:
    mislog.log('crit','The requested action is not defined: %s' % action)
  return action_yaml

### Show_list: list the actions available for this environment
# Along with any parameters
def show_list(mislog, args, env_yaml):
  if args.action == 'list':
    print "\n-----------------"
    for action in env_yaml['makeitso']:
      extra = ""
      try:
        for key in env_yaml['makeitso'][action]['parameters']:
          extra += "%s[=%s] " % (key, env_yaml['makeitso'][action]['parameters'][key])
      except:
        pass

      print "task> %s %s" % (action, extra)
    print "-----------------"
    print ""
    exit(0)
  else:
    return

### sub_params: Perform substitutions of the passed parameters
### into the execution sections
def sub_params(mislog, env_yaml, params):
    final_params = {}

    # Set defaults from the yaml
    for param in env_yaml['parameters']:
        final_params[param] = env_yaml['parameters'][param]
        mislog.log('debug',"Default parameter %s is %s" % (param, env_yaml['parameters'][param]))

    # Override with the cl args
    for param_string in params.split(','):
        param, value = params.split('=')
        final_params[param] = value
        mislog.log('debug',"Given parameter %s is %s" % (param, value))

    for index, command in enumerate(env_yaml['command']):
      mislog.log('debug',"Substitution yaml: %s" % final_params)
      for param, value in final_params.iteritems():
        command = command.replace(("__%s__" % param),value)
      env_yaml['command'][index] = command
    return env_yaml

### parse_validate: Ensure we are about to do something valid
def parse_validate(mislog, args, yaml):

  # Do we have an environment
  try:
    args.environment
  except:
    mislog.log('crit','Parser failed for environment: %s' % args['environment'])

  # Is our action valid for our environment
  try:
    yaml['makeitso'][args.action]
  except:
    if args.action == 'list':
      pass
    else:
      mislog.log('crit','Parser failed. Cant find action %s' % args.action)

  # Do our parameters exist in our job
  if args.params :
    for param_string in args.params.split(','):
      param, value = args.params.split('=')
      if param not in yaml['makeitso'][args.action]['parameters']:
          mislog.log('crit','Parser failed. Your parameter is not defined in the job')
    


### arg_parser: Handle command-line arguments
def arg_parser():

  parser = argparse.ArgumentParser(description='A program to orchestrates remote deployments based on yaml')
  parser.add_argument('environment',
                    help='Specify environment for action')
  parser.add_argument('action',
                    help='Execute deployment action')
  parser.add_argument('-t', '--time',
                    help='Timespec: [[dd:mm:yy] HH:MM] [daily] [hourly] [* * * * *]')
  parser.add_argument('-s', '--checksum',
                    help='Checksum of the yaml to be executed',
                    default='nohashcheck')
  parser.add_argument('-u', '--user',
                    help='Execute action as user [user]',
                    default=pwd.getpwuid(os.getuid())[0])
  parser.add_argument('params',
                    help='Specify deployment parameters: [key=value]',
                    nargs='?')
  parser.add_argument('-q', '--quiet',
                    help='Quiet mode. No messaging. Cannot be used with -d. Default off',
                    const=True,
                    default=False,
                    action='store_const')
  parser.add_argument('-v', '--verbose',
                    help='Verbose mode. Additionally logs to STDOUT. Default off',
                    const=True,
                    default=False,
                    action='store_const')
  parser.add_argument('-l', '--logfile',
                    help='File for logging. Defaults to syslog',
                    default='_syslog')
  parser.add_argument('-c', '--config',
                    help='Specify alternate config file. Defaults to /etc/makeitso/makeitso.d/*.yaml',
                    default='/etc/makeitso/makeitso.d')
  return (parser.parse_args())

