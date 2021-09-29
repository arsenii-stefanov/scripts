### Ingress TargetGroup Actualiser

This script is created as a workaround for an issue with AWS Ingress Controller that we have recently faced.
Since we use the NodePort resource type as a backend for the Ingress, when a new microservice is added to the K8s cluster, which means that a new Ingress is created, the AWS Ingress Controller adds a corresponding firewall rule to the SecurityGroup attached to all K8s nodes (EC2 instances) on the cluster.
When we hit the default limit of 100 rules per SecurityGroup, we had this limit raised to 200 rules, and when this limit was reached too, AWS Support said that they could raise it to 300 only if we allow them to decrease the number of SecurityGroups that can be attached to one EC2 instance, which did not work for us.
While we discussed separating our microversives between different node pools or clusters, I decided to create such a workaround.

The script should do the following:

1. Find all Pods where a specific microservice is running and get their parent nodes
2. Get EC2 instance IDs of the nodes
3. Get the TargetGroup created for the microservice
4. Add the nodes to the TargetGroup as targets
5. Remove old nodes that no longer have Pods with the microservice from the TargetGroup (basically, this step is not obligatory, since the NodePort is accessible from any node through a corresponding port)

Example:

```
$ ./ingress-tg-actualiser.py --kube-namespace=file-generation --app-name=file-generation --app-env=qa-next

[INFO] Checking if the script is running on an EC2 instance.
[INFO] This is not an EC2 instance.
[INFO] AWS secret key environment vaiables not found. Trying to use AWS SSO for API authentication
[INFO] Checking connection to AWS API
[INFO] Successfuly connected to AWS API
[INFO] No Kubernetes API Credentials found. Trying to use a configuration file
[INFO] Checking connection to Kubernetes API
[INFO] Successfuly connected to Kubernetes API
[INFO] Obtaining Kubernetes node names
['ip-172-18-99-206.us-east-2.compute.internal']
[INFO] Obtaining EC2 instance IDs for Kubernetes nodes
['i-XXXXXXXXXXXXXXXXX']
[INFO] Obtaining AWS TargetGroup ARNs
['arn:aws:elasticloadbalancing:us-east-2:XXXXXXXXXXXX:targetgroup/k8s-filegene-qanextfi-ac6381ff29/db698cc3c6651342']
[INFO] Registering targets in TargetGroups
[INFO] Registering target i-XXXXXXXXXXXXXXXXX in the TargetGroup arn:aws:elasticloadbalancing:us-east-2:XXXXXXXXXXXX:targetgroup/k8s-filegene-qanextfi-ac6381ff29/db698cc3c6651342
{'ResponseMetadata': {'RequestId': '3d270a2d-633e-40ab-910d-0711d4cde42b', 'HTTPStatusCode': 200, 'HTTPHeaders': {'x-amzn-requestid': '3d270a2d-633e-40ab-910d-0711d4cde42b', 'content-type': 'text/xml', 'content-length': '253', 'date': 'Mon, 27 Sep 2021 16:37:15 GMT'}, 'RetryAttempts': 0}}
[INFO] Deregistering inactive targets from TargetGroups
[INFO] Obtaining existing targets in the TargetGroup arn:aws:elasticloadbalancing:us-east-2:XXXXXXXXXXXX:targetgroup/k8s-filegene-qanextfi-ac6381ff29/db698cc3c6651342
['i-XXXXXXXXXXXXXXXXX', 'i-YYYYYYYYYYYYYYYYY']
[INFO] Checking if each existing target has a running Pod of our application
[INFO] Target i-XXXXXXXXXXXXXXXXX is valid. Keeping it
[INFO] Target i-YYYYYYYYYYYYYYYYY is invalid. Deregistering it from the TargetGroup arn:aws:elasticloadbalancing:us-east-2:XXXXXXXXXXXX:targetgroup/k8s-filegene-qanextfi-ac6381ff29/db698cc3c6651342
{'ResponseMetadata': {'RequestId': '2b86f365-06c6-4ee3-ac4a-a31da62a9fe8', 'HTTPStatusCode': 200, 'HTTPHeaders': {'x-amzn-requestid': '2b86f365-06c6-4ee3-ac4a-a31da62a9fe8', 'content-type': 'text/xml', 'content-length': '259', 'date': 'Mon, 27 Sep 2021 16:37:16 GMT'}, 'RetryAttempts': 0}}
```
