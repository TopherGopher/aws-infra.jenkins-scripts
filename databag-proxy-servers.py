#!/usr/bin/python
import databag
import click
import os
import hvac
import requests.packages.urllib3

#### Logic for taking servers in and out of rotation ####
#Here's the servers array:
# bag['production']['webcluster01']['servers'] = [
#   "server web01.newmediadenver.com:80;",
#   "server web02.newmediadenver.com:80;",
#   "server web04.newmediadenver.com:80;"
# ]
def get_vault_client():
    """
    Return a vault client if possible.
    """
    # Disable warnings for the insecure calls
    requests.packages.urllib3.disable_warnings()
    vault_addr = os.getenv("VAULT_ADDR", "https://sanctuary.drud.io:8200")
    vault_token = os.getenv('GITHUB_TOKEN', False)
    if not vault_addr or not vault_token:
        print "You must provide both VAULT_ADDR and GITHUB_TOKEN environment variables."
        print "(Have you authenticated with `drud secret auth` to create your GITHUB_TOKEN?)"
        sys.exit(1)

    vault_client = hvac.Client(url=vault_addr, verify=False)
    vault_client.auth_github(vault_token)

    if vault_client.is_initialized() and vault_client.is_sealed():
        print "Vault is initialized but sealed."
        sys.exit(1)

    if not vault_client.is_authenticated():
        print "Could not get auth."
        sys.exit(1)

    return vault_client

def remove_server(servers, server_to_remove, cluster):
  """
  Removes a server from the list.

  :param servers: The url entry to add to the databag
  :param server_to_remove: The name of just the server or the full server string

  :returns list of servers
  """
  index_to_remove = None
  if servers == None or not isinstance(servers, list):
    print "No servers are in rotation for '{cluster}'".format(cluster=cluster)
    return []
  for index, server in enumerate(servers):
    if server_to_remove in server:
      index_to_remove = index
      break
  if index_to_remove is not None:
    servers.pop(index_to_remove)
  else:
    print "Could not find server {server} in {cluster}[{servers}] to remove.".format(server=server_to_remove,cluster=cluster,servers=",".join(servers))

  print "Remaining servers: [%s]" % ','.join(servers)
  return servers

def add_server(servers, server_to_add, cluster):
  """
  Add a server to the list.

  :param servers: The url entry to add to the databag
  :param server_to_add: The name of just the server or the full server string

  :returns list of servers
  """
  # Fix the format if necessary
  if "server " not in server_to_add:
    server_to_add="server {server}".format(server=server_to_add)
  if ":80;" not in server_to_add:
    server_to_add="{server}:80;".format(server=server_to_add)

  # Check for the "None" edgecase
  if servers == None or len(servers) == 0:
    print "No servers are in rotation for '{cluster}'".format(cluster=cluster)
    servers=[]
  if any([server_to_add==server for server in servers]):
    print "Server {cluster}['{server}]' already exists in rotation. No action is required".format(cluster=cluster,server=server_to_add)
    return servers
  else:
    print "Adding server '{server}' to {cluster}.".format(server=server_to_add, cluster=cluster)
    servers.append(server_to_add)
  return servers

def get_server_list(environment):
  """
  Get the list of servers for an environment

  :param environment: 'staging' or 'production'

  :returns list of servers
  """
  vault_client = get_vault_client()
  proxy_databag = vault_client.read("secret/databags/nmdproxy/upstream")['data']
  if environment=='production':
    server_list = proxy_databag[environment]['webcluster01']['servers']
  elif environment=="staging":
    server_list = proxy_databag[environment]['web01']['servers']
  else:
    raise Exception("Unrecognized environment of '{environment}. Available options are 'production' and 'development'".format(environment=environment))
    return None
  return server_list

@click.command()
@click.option('--server', prompt="Server name:", help="Name of the server you would like to add/remove")
@click.option('--add', 'operation', flag_value='add', default=True)
@click.option('--remove', 'operation', flag_value='remove')
@click.option('--debug', 'debug', flag_value=True, default=False)
def modify_server_list(server, operation, debug):
  """
  Get the list of servers for an environment
  """
  vault_client = get_vault_client()
  proxy_databag = vault_client.read("secret/databags/nmdproxy/upstream")['data']
  environment = "staging" if "nmdev.us" in server else "production"
  if environment=="production":
    cluster='webcluster01'
  elif environment=="staging":
    cluster='web01'
  else:
    raise Exception("Unrecognized environment of '{environment}. Available options are 'production' and 'development'".format(environment=environment))
    return None
  server_list = proxy_databag[environment][cluster]['servers']
  if server_list is None:
    print "server_list is None"
  if operation == "add":
    server_list = add_server(server_list, server, cluster)
  elif operation == "remove":
    server_list = remove_server(server_list, server, cluster)
  else:
    print "Unrecognized server operation of '{operation}'".format(operation=operation)
  # Put it all back together
  proxy_databag[environment][cluster]['servers'] = server_list

  vault_client.write("secret/databags/nmdproxy/upstream", **proxy_databag)

  return True

# if __name__ == '__main__':
#   modify_server_list(server="fakeweb07.newmediadenver.com", environment="production", operation="add")
#   modify_server_list(server="fakeweb06.nmdev.us", environment="staging", operation="add")
if __name__ == '__main__':
  modify_server_list()
