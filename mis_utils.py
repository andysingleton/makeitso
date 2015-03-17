import argparse
import pwd
import os
import syslog
import yaml
import paramiko
import socket

def execute_action(args, task):
  jobuser = task['user']
  jobs = task['command']
  servers = task['servers']
  cwd = task['cwd']
  failcontinue = task['failcontinue']

  for server in servers:
    logger(args, 'info', 'Connecting to: '+server)
    addr = socket.gethostbyname(server)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(addr,username='makeitso', key_filename='/etc/makeitso/deploy')
    try:
      channel = ssh.invoke_shell()
      channel.set_combine_stderr(True)
      stdin = channel.makefile('wb')
      stdout = channel.makefile('rb')
    except:
      logger(args,'critical','Could not run remote command on '+server)
    for comm in task['command']:
      command="sudo su - %s\n" % jobuser
      command+="cd %s\n" % cwd
      command+=comm
      command+="\n exit\n exit\n"
      logger(args, 'debug', 'Executing: '+command)
      try:
        stdin.write(command)
        outstring=stdout.read()
        logger(args, 'debug', 'Console output: '+outstring)
      except:
        if failcontinue == False:
          stdout.close()
          stdin.close()
          ssh.close
          logger(args,'critical',('Server %s could not finish: %s' % ( server, comm)))
        else:
          logger(args,'warn',('Server %s could not finish: %s' % ( server, comm)))
    stdout.close()
    stdin.close()
    ssh.close
  return

def validate_everything(args, yaml_object):
  validate_environment(args, yaml_object)
  validate_user(args, yaml_object)
  validate_action(args, yaml_object)

def validate_user(args, yaml_object):
  print 'null check'

def validate_action(args, yaml_object):
  environment = args.environment
  action = args.action
  actionlist = []
  for keys in yaml_object[environment]:
    actionlist.append(keys['action'])
  if action not in actionlist:
    logger(args,'critical',('Could not find action %s' % action ))
      
def validate_environment(args, yaml_object):
  environment = args.environment
  try:
    yaml_object[environment]
    logger(args, 'info', 'Environment: '+environment)
  except:
    logger(args, 'critical', 'Can\'t find the environment: '+environment)

### validate_strings: Ensure all required yaml elements are present
def validate_strings(args, item, listit):
  for listitem in listit:
    try:
      item[listitem]
    except:
      logger(args, 'critical', 'YAML definition requires these items: '+str(listit))

def default_items(args, item, mydict):
  for key, value in mydict.iteritems():
    try:
      item[key]
    except:
      logger(args, 'debug', 'Defaulting '+key+' to '+str(value))
      item[key]=value
  return(item)


### get_roles:Get roles attributed to the user
def get_roles(args, user,  yaml_object):
  environment = args.environment
  privlist = []

  for item in yaml_object['environments'][environment]:
    if item['type'] == 'role':
      for itemuser in item['users']:
        if itemuser == user:
          for roleitem in yaml_object['roles'][item['name']]:
            privlist.append(roleitem)
  
  return(privlist)

### get_tasks: Find all tasks for an environment and action
def get_task(args, yaml_object):
  environment = args.environment
  action = args.action

  for item in yaml_object[environment]:
    try:
      item['action']
      validate_strings(args, item, ['servers', 'allowed', 'cwd', 'command'])
      item=default_items(args, item, {'failcontinue': False, 'user': 'root', 'required_version': False})
      return(item)
    except:
      pass

  logger(args, 'critical', 'The action {} is not defined for environment {}.',action,environment)
 

  #elif item['type'] == 'options':
  #  item=default_items(args, item, {'tagged-only': False})
  #elif item['type'] == 'role':
  #  validate_strings(args, item, ['name', 'users'])
  #else:
  #  logger(args, 'critical', 'YAML action block '+item['namecontained no \'type\'')

  # print  yaml_object['environments'][environment]

  

  

### get_all_configs: iterate over all yaml files ###
def get_all_configs( args ):
  try:
    interlist = os.listdir(args.config)
    logger(args, 'debug', 'Reading configs from '+args.config)
  
  except:
    logger(args, 'critical', 'Can\'t read the configuration directory: '+args.config)
  filelist = []

  for myfile in interlist:
    if myfile.endswith('.yaml'):
      filelist.append(myfile)

  if len(filelist) == 0:
    logger(args, 'critical', 'Can\'t read any yaml files from configuration directory: '+args.config)

  yaml_object = {}

  for myfile in filelist:
    yaml_object.update(parse_file(args, args.config+'/'+myfile))

  return yaml_object


### parse_file: load specific yaml files ###
def parse_file(args, myfile):
  file_object = open(myfile,'r')
  try:
    return (yaml.load(file_object))
  except:
    logger(args, 'warn', 'invalid YAML in file '+myfile)
    return ({})


### logger: Logging handler ###
def logger( args, level, message ):

  if level =='critical':
    loglevel = syslog.LOG_ERR
    score=4
  if level == 'warn':
    loglevel = syslog.LOG_WARNING
    score=3
  if level == 'info':
    loglevel = syslog.LOG_INFO
    score=3
  if level == 'debug':
    loglevel = syslog.LOG_DEBUG
    score=1

  threshold = 3

  if args.quiet == True:
    threshold=5
  if args.verbose == True:
    threshold=1

  if (threshold-1) <= score:
    syslog.syslog(syslog.LOG_ERR, message)
  if threshold <= score:
    print level+': '+message

  if level == 'critical':
    exit(1)


### arg_parser: Handle command-line arguments
def arg_parser():

  parser = argparse.ArgumentParser(description='A program to orchestrates remote deployments based on yaml')
  parser.add_argument('action',
                    help='Execute deployment action')
  parser.add_argument('-e', '--elevate',
                    help='Internal use. To be removed')
  parser.add_argument('-u', '--user',
                    help='Execute action as user [user]',
                    default=pwd.getpwuid(os.getuid())[0])
  parser.add_argument('environment',
                    help='Specify environment for action')
  parser.add_argument('version',
                    help='Specify tag or version for code',
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
  parser.add_argument('-k','--key',
                    help='Give an alternate ssh key for communications',
                    default='/etc/makeitso/deploy.key')
  return (parser.parse_args())

