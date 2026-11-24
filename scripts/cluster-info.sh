# Service deployments and KEDA
kubectl --context twolevel-dev -n retailstore get deployments,pods
kubectl --context twolevel-dev -n retailstore get scaledobjects,hpa

# Karpenter NodePool, EC2NodeClass, NodeClaim, and Nodes
kubectl --context twolevel-dev get nodepool,ec2nodeclass,nodeclaims
kubectl --context twolevel-dev get nodes -o wide

# Monitoring
kubectl --context twolevel-dev -n monitoring get pods,services