#!/usr/local/bin/python3

import kubernetes    ### main module for communication with Kubernetes API
import boto3         ### main module for communication with AWS API 
import botocore      ### this module is used for handling boto3 exceptions (API errors)
import os            ### this module is used for environment variables
import argparse      ### module for parsing command line arguments
import requests      ### module for sending HTTP requests

#########################
###     Variables     ###
#########################
kube_config_file = "~/.kube/config"

aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_default_region = os.getenv("AWS_DEFAULT_REGION", 'us-east-2')
aws_profile = os.getenv("AWS_PROFILE", 'dev')
aws_metadata_server_url = 'http://169.254.169.254'

#########################
###     Functions     ###
#########################

def arg_parser():
	parser = argparse.ArgumentParser()
	parser.add_argument('--log-level', type=str, help='Log level. Could be one of: verbose', default='')
	parser.add_argument('--kube-namespace', type=str, required=True, help='Kubernetes namespace where your application is located')
	parser.add_argument('--app-name', type=str, required=True, help='Name of you application in Kubernetes')
	parser.add_argument('--app-env', type=str, required=True, help='Name of the environment where your application is running')
	args = parser.parse_args()

	return args

def log(var, msg: str = ""):
	if log_level == "verbose":
		print("[DEBUG LOG] " + msg)
		print(var)

def kube_create_api_client_default(api_key: str = '', api_host: str = '', config_file: str = ''):

	### If Kubernetes API token is used for authentication
	if api_key and api_host:
		configuration = kubernetes.client.Configuration()
		configuration.api_key['authorization'] = api_key
		configuration.host = api_host
	### If a local config file is used for authentication
	elif config_file:
		print("[INFO] No Kubernetes API Credentials found. Trying to use a configuration file")
		try:
			configuration = kubernetes.config.load_kube_config(config_file=config_file)
		except kubernetes.config.config_exception.ConfigException as e:
			print("[ERROR]", e)
			exit(1)

	### Create an API client for further API calls
	global kube_api_client_default
	kube_api_client_default = kubernetes.client.ApiClient(configuration)

def kube_test_connection(api_client):
	try:
		### Check whether the Kubernetes API service is reachable and we have access to it by requesting a list of existing Namespaces. If not - abort script execution
		print("[INFO] Checking connection to Kubernetes API")
		kubernetes.client.CoreV1Api(api_client).list_namespace()
	except kubernetes.client.exceptions.ApiException as e:
		print("[ERROR] Could not access Kubernetes API. Likely, your credentials are invalid. See full error message below", e, sep='\n')
		exit(1)
	else:
		print("[INFO] Successfuly connected to Kubernetes API")

def kube_get_node_names(api_client, namespace: str, label_selector: str) -> list:

	### Create an API instance with credentials that were set earlier
	api_instance = kubernetes.client.CoreV1Api(api_client)

	### Send an API request to get a list of Pods in the current Namespace
	pods = api_instance.list_namespaced_pod(namespace=namespace, label_selector=label_selector, watch=False)

	node_list = []

	for i in pods.items:
		log(i.spec.node_name, "Kubernetes node name")
		node_list.append(i.spec.node_name)

	log(node_list, "Kubernetes node names")
	return node_list

def kube_get_tg_arns(api_client, namespace: str, group: str, version: str, plural: str, label_selector: str) -> list:

	### Create an API instance with credentials that were set earlier
	api_instance = kubernetes.client.CustomObjectsApi(api_client)
	
	### Send an API request to get a list of TargetGroupBindings (Custom Object) in the current Namespace
	tgb_list = api_instance.list_namespaced_custom_object(
		namespace=namespace,
		group=group,
		version=version,
		plural=plural,
		label_selector=label_selector
	)

	tg_list = []

	for i in tgb_list['items']:
		tg_arn = i['spec']['targetGroupARN']
		log(tg_arn, "EC2 TargetGroup ARN")
		tg_list.append(tg_arn)

	log(tg_list, "EC2 TargetGroup ARNs")
	return tg_list

def aws_create_session_default(region=aws_default_region):

	global aws_session_default

	try:
		### If metadata server is reachable, then this means that the script is on an EC2 instance. If so, then an IAM token should be used
		print("[INFO] Checking if the script is running on an EC2 instance.")
		metadata_server = requests.get(url=aws_metadata_server_url, timeout=2)
	except requests.exceptions.ConnectTimeout as e:
		### If we are not on an EC2 instance and if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are set via environment variables, use them as credentials
		print("[INFO] This is not an EC2 instance.")
		if aws_access_key_id and aws_secret_access_key and region:
			print("[INFO] Found AWS secret key environment vaiables. Using them for API authentication")
			aws_session_default = boto3.Session(
				aws_access_key_id=aws_access_key_id,
				aws_secret_access_key=aws_secret_access_key,
				region_name=region
			)
		### If we are neither on an EC2 instance nor AWS credentials are set via environment variables, then try using AWS SSO
		elif aws_profile and region:
			print("[INFO] AWS secret key environment vaiables not found. Trying to use AWS SSO for API authentication")
			aws_session_default = boto3.Session(
				profile_name=aws_profile,
				region_name=region
			)
		else:
			print("[ERROR] One of the followng set of environment variables should be set for accessing AWS API:", "AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION", "AWS_PROFILE, AWS_DEFAULT_REGION", sep="\n")
			print("Alternatively, you can run the script on an EC2 instance with an appropriate IAM role attached. If it is already on an EC2 instance, then connection to the metadata server timed out.")
			exit(1)
	else:
		print("[INFO] Running on an EC2 instance. IAM token from the metadata will be used for API authentication.")

def aws_test_connection(session):

  ### Check if we are authenticated
  api_instance = session.client('sts')

  try:
  	print("[INFO] Checking connection to AWS API")
  	api_instance.get_caller_identity()
  except botocore.exceptions.SSOTokenLoadError as e:
  	print(e)
  	exit(1)
  else:
  	print("[INFO] Successfuly connected to AWS API")

def aws_get_instance_ids(session, private_dns_names: list = [], private_dns_name: str = '', tag_key: str = '', tag_value: str = '') -> list:

	### Create an API instance (credentials, region, resource type)
	api_instance = session.resource('ec2')

	### Send an API request to get a list of EC2 instances matching the filter 
	if private_dns_names:
		ec2_list = []
		for dns_name in private_dns_names:
			log(dns_name, "Kube node DNS name")
			ec2_instances = api_instance.instances.filter(
				Filters=[{'Name': 'private-dns-name', 'Values': [dns_name]}])
			for i in ec2_instances:
				log(i.id, "EC2 instance ID")
				ec2_list.append(i.id)
		log(ec2_list, "EC2 Instance IDs")
		return ec2_list

	elif private_dns_name:
		ec2_instances = api_instance.instances.filter(
			Filters=[{'Name': 'private-dns-name', 'Values': [private_dns_name]}])

		ec2_list = []

		for i in ec2_instances:
			log(i.id, "EC2 instance ID")
			ec2_list.append(i.id)
		
		log(ec2_list, "EC2 Instance IDs")
		return ec2_list

	elif tag_key and tag_value:
		t_key = 'tag:' + tag_key
		t_value = tag_value
		ec2_instances = api_instance.instances.filter(
			Filters=[{'Name': t_key, 'Values': [t_value]}])

		ec2_list = []

		for i in ec2_instances:
			log(i.id, "EC2 instance ID")
			ec2_list.append(i.id)

		log(ec2_list, "EC2 Instance IDs")
		return ec2_list


def aws_register_targets(session, tg_arns: list, target_ids: list):

	### Create an API instance (credentials, region, resource type)
	api_instance = session.client('elbv2')

	### Send an API request to register EC2 instances in the TargetGroup
	for arn in tg_arns:
		for id in target_ids:
			print("[INFO] Registering target " + id + " in the TargetGroup " + arn)
			response = api_instance.register_targets(
				TargetGroupArn=arn,
				Targets=[
					{
						'Id': id,
			        },
			    ]
			)
			print(response)


def aws_deregister_targets(session, tg_arns: list, target_ids: list):

	### Create an API instance (credentials, region, resource type)
	api_instance = session.client('elbv2')

	### Send an API request to deregister EC2 instances from the TargetGroup
	for arn in tg_arns:
		print("[INFO] Obtaining existing targets in the TargetGroup " + arn)
		existing_targets = api_instance.describe_target_health(TargetGroupArn=arn)

		existing_target_ids = []

		for i in existing_targets['TargetHealthDescriptions']:
			id = i['Target']['Id']
			log(id, "Existing Target ID")
			existing_target_ids.append(id)

		print(existing_target_ids)

		print("[INFO] Checking if each existing target has a running Pod of our application")
		for et in existing_target_ids:
			if et in target_ids:
				print("[INFO] Target " + et + " is valid. Keeping it")
			else:
				print("[INFO] Target " + et + " is invalid. Deregistering it from the TargetGroup " + arn)
				response = api_instance.deregister_targets(
					TargetGroupArn=arn,
					Targets=[
						{
							'Id': et,
				        },
				    ]
				)
				print(response)


###########################
###     Main script     ###
###########################

### Run the commands below only if this script is executed directly (__name__ == '__main__'). If it is imported to another script, the bellow commands will not be executed.
if __name__ == "__main__":

    ### Parse command line arguments as variables
	args = arg_parser()
	log_level = args.log_level
	kube_namespace = args.kube_namespace
	app_name = args.app_name
	app_env = args.app_env

	app_label_instance = "app.kubernetes.io/instance=" + app_env + "-" + app_name
	app_label_stack_name = "ingress.k8s.aws/stack-name=" + app_env + "-" + app_name

    ### Create an AWS API session and test the connection
	aws_create_session_default()
	aws_test_connection(aws_session_default)

	### Create a Kubernetes API client and test the connection
	kube_create_api_client_default(config_file=kube_config_file)
	kube_test_connection(api_client=kube_api_client_default)

	### Get the names of Kubernetes nodes where Pods with our application are located
	print("[INFO] Obtaining Kubernetes node names")
	kube_node_names = kube_get_node_names(api_client=kube_api_client_default, namespace=kube_namespace, label_selector=app_label_instance)
	print(kube_node_names)

	### Get the IDs of EC2 instances matching the hostnames of the Kubernetes nodes
	print("[INFO] Obtaining EC2 instance IDs for Kubernetes nodes")
	ec2_instance_ids = aws_get_instance_ids(session=aws_session_default, private_dns_names=kube_node_names)
	print(ec2_instance_ids)

	### Get the ARN of the TargetGroup associated with the K8s Service (NodePort) created for our application
	print("[INFO] Obtaining AWS TargetGroup ARNs")
	tg_arns = kube_get_tg_arns(api_client=kube_api_client_default, namespace=kube_namespace, group="elbv2.k8s.aws", version="v1beta1", plural="targetgroupbindings", label_selector=app_label_stack_name)
	print(tg_arns)

	### Register new EC2 instances in the TargetGroup
	print("[INFO] Registering targets in TargetGroups")
	aws_register_targets(session=aws_session_default, tg_arns=tg_arns, target_ids=ec2_instance_ids)

	### Deregister old EC2 instances from the TargetGroup
	### Technically, since we use NodePort as a backend for Ingress, we can access the K8s Service from any node (EC2-instance) on the cluster by using the right port
	### Thus, we have this step just for keeping things in order
	print("[INFO] Deregistering inactive targets from TargetGroups")
	aws_deregister_targets(session=aws_session_default, tg_arns=tg_arns, target_ids=ec2_instance_ids)