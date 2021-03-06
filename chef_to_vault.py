#!/usr/bin/env python

import yaml
import os
import sys
import hvac
import databag
import click
from pprint import pprint as p
import requests.packages.urllib3

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

@click.command()
@click.option('--dest', default="secret/databags")
@click.option('--debug', is_flag=True)
def sync(dest, debug):
    """
    This is designed to sync databags by using the destination path.
    If the destination is a container, it will sync the entire container
    If the destination is a full bag path, it will sync the entire bag
    """
    vault_client = get_vault_client()
    containers = {}
    # If they didn't pass in a secret/ path, prepend it
    if not dest.startswith("secret/"):
        dest = os.path.join("secret", dest)
    # If the dest is 
    if not dest.startswith('secret/databags'):
        exit('The dest needs to start with "secret/databags" and is designed to sync by container, or even single bag name.')
    # If we're just doing a single bag in nmdhosting
    if len(os.path.split(dest)) == 4:
        _, _, container, bag_name = dest.split('/')
        # Construct the data structure we can use below
        containers[container] = [bag_name]
    # If we're doing a container's worth of databags
    elif dest.startswith('secret/databags') and len(os.path.split(dest)) == 3:
        _, _, container = dest.split('/')
        containers[container] = []

    # If we're doing ALL containers
    elif dest == "secret/databags":
        containers = {x: [] for x in databag.run_cmd(op="list")}
    # We're going to do something else
    else:
        exit("Need to add logic for migrating {dest}".format(dest=dest))

    
    # There's only one container and one bag, we don't need to do anything
    if len(containers) == 1 and len(containers[0]) == 1:
        pass
    # If there's more than one container set, we need to get the bags for each container
    else:
        for container, bags in containers.iteritems():
            bag_names = databag.run_cmd(op="show", container=container)
            containers[container] = bag_names
        
    # For each container we found
    for container, bag_names in containers.iteritems():
        for bag_name in bag_names:
            print "Migrating chef databag '{container}/{bag}' to vault path '{dest}/{container}/{bag}'".format(
                container=container,
                bag=bag_name,
                dest=dest
            )
            bag = databag.get_databag(bag_name, container)
            if not debug:
                if bag_name == "certs" and container == "nmdproxy":
                    print "Breaking up certs into individual secrets (b/c of space constraints)."
                    # Since we're breaking this into multiple bags, just don't worry about it.
                    del bag["id"]
                    # For each environment's certs
                    for env in bag.keys():
                        # For each site in nmdcerts/
                        for site in bag[env].keys():
                            vpath = "secret/databags/nmdproxy/certs/{0}/{1}".format(env, site)
                            print "\tCreating cert nmdproxy/{0}/{1}".format(env, site)
                            print vpath
                            vault_client.write(vpath, **bag[env][site])
                elif isinstance(bag, dict):
                    vault_client.write(os.path.join(dest, container, bag_name), **bag)
                elif isinstance(bag, basestring):
                    print "The databag {bag} has no content...Creating an empty space...".format(bag=bag_name)
                    vault_client.write(os.path.join(dest, container, bag_name), value=bag)
                else:
                    print "We don't know what to do with this bag"
                    p(bag)


if __name__ == '__main__':
    sync()
