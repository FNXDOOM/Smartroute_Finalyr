# Amazon ECS Fargate Production Deployment Guide

This directory contains task-definition templates for deploying SmartRouteAI to AWS ECS Fargate with separate API and worker services, Docker Hub registry, Application Load Balancer, and secure secret management.

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [One-Time AWS Setup](#one-time-aws-setup)
- [Configuration & Secrets](#configuration--secrets)
- [Task Definition Deployment](#task-definition-deployment)
- [Monitoring & Troubleshooting](#monitoring--troubleshooting)
- [Updating & Rollback](#updating--rollback)

---

## Architecture

```
Internet
   ↓
Application Load Balancer (ALB) on port 443 (HTTPS)
   ↓
┌─────────────────────────────────────────────────┐
│  ECS Fargate Cluster                            │
├─────────────────────────────────────────────────┤
│  Service: smartroute-api                        │
│  ├─ Task: uvicorn main:app (port 8000)         │
│  ├─ Replicas: 2+ (auto-scale based on CPU)     │
│  ├─ Health check: GET /health/ready every 30s  │
│  └─ Secrets: DATABASE_URL, CLERK_*, STADIA_*   │
├─────────────────────────────────────────────────┤
│  Service: smartroute-worker                     │
│  ├─ Task: python worker.py (no HTTP)           │
│  ├─ Replicas: 1 (fixed, only one worker)       │
│  └─ Secrets: DATABASE_URL, CLERK_*              │
└─────────────────────────────────────────────────┘
   ↓
Supabase PostgreSQL (external managed database)
```

### Service Separation

- **smartroute-api**: Handles HTTP requests and WebSocket connections
  - Attached to ALB target group
  - Auto-scales based on CPU/memory metrics
  - No direct database access to secrets; reads from Secrets Manager

- **smartroute-worker**: Runs scheduled background jobs
  - No public listener; internal to cluster
  - Single task replica (ensures jobs don't run in parallel)
  - Same secrets access as API

---

## Prerequisites

1. **AWS Account** with:
   - ECS service role permissions
   - EC2 Container Registry (ECR) or Docker Hub access
   - Secrets Manager permissions
   - CloudWatch Logs permissions
   - ALB and target group setup

2. **Docker Hub Account** with a private repository (e.g., `youruser/smartrouteai`)

3. **Database**: Supabase or managed RDS PostgreSQL (must be externally accessible)

4. **Clerk Account**: For authentication (JWT issuer, JWKS URL)

5. **Stadia Maps Account**: For maps and routing (API key)

6. **AWS CLI** installed and configured: `aws configure`

7. **Docker** installed locally for building and pushing images

---

## One-Time AWS Setup

### Step 1: Create Docker Hub Image

Build the Docker image locally and push to Docker Hub:

```bash
# Login to Docker Hub
docker login

# Build the image
docker build -t smartrouteai:latest .

# Tag for Docker Hub
docker tag smartrouteai:latest ${DOCKERHUB_USERNAME}/smartrouteai:1.0.0

# Push to Docker Hub
docker push ${DOCKERHUB_USERNAME}/smartrouteai:1.0.0

# Also tag as "latest"
docker tag smartrouteai:latest ${DOCKERHUB_USERNAME}/smartrouteai:latest
docker push ${DOCKERHUB_USERNAME}/smartrouteai:latest
```

Docker Hub image URL: `${DOCKERHUB_USERNAME}/smartrouteai:1.0.0`

### Step 2: Create Secrets Manager Secrets

Create 4 secrets in AWS Secrets Manager (same region as ECS cluster):

```bash
# 1. Database connection string
aws secretsmanager create-secret \
  --name smartrouteai/production/database-url \
  --secret-string "postgresql://user:password@host:5432/smartrouteai" \
  --region ${AWS_REGION}

# 2. Clerk JWKS URL
aws secretsmanager create-secret \
  --name smartrouteai/production/clerk-jwks-url \
  --secret-string "https://your-clerk-instance.clerk.accounts.com/.well-known/jwks.json" \
  --region ${AWS_REGION}

# 3. Clerk Issuer
aws secretsmanager create-secret \
  --name smartrouteai/production/clerk-issuer \
  --secret-string "https://your-clerk-instance.clerk.accounts.com" \
  --region ${AWS_REGION}

# 4. Docker Hub credentials
aws secretsmanager create-secret \
  --name smartrouteai/production/dockerhub-credentials \
  --secret-string '{"username":"your-dockerhub-user","password":"your-dockerhub-access-token"}' \
  --region ${AWS_REGION}
```

**Note:** Use a Docker Hub personal access token, not your password. Generate one at https://hub.docker.com/settings/security.

### Step 3: Create CloudWatch Log Groups

```bash
aws logs create-log-group \
  --log-group-name /ecs/smartroute-api \
  --region ${AWS_REGION}

aws logs create-log-group \
  --log-group-name /ecs/smartroute-worker \
  --region ${AWS_REGION}

# Set retention (optional, e.g., 30 days)
aws logs put-retention-policy \
  --log-group-name /ecs/smartroute-api \
  --retention-in-days 30 \
  --region ${AWS_REGION}
```

### Step 4: Create IAM Task Execution Role

The task execution role allows ECS to pull images and access Secrets Manager:

```bash
# Create role
aws iam create-role \
  --role-name ecsTaskExecutionRole-smartrouteai \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": "ecs-tasks.amazonaws.com"
        },
        "Action": "sts:AssumeRole"
      }
    ]
  }' \
  --region ${AWS_REGION}

# Attach the built-in policy for basic ECS task execution
aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole-smartrouteai \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Attach the custom Secrets Manager policy (see file: ecs-task-execution-secrets-policy.json)
aws iam put-role-policy \
  --role-name ecsTaskExecutionRole-smartrouteai \
  --policy-name SmartRouteSecretsPolicy \
  --policy-document file://ecs-task-execution-secrets-policy.json
```

The role ARN will be used in the task definition.

### Step 5: Create ECS Cluster

```bash
aws ecs create-cluster \
  --cluster-name smartroute-prod \
  --region ${AWS_REGION}
```

### Step 6: Create Application Load Balancer (ALB) & Target Groups

If you don't already have an ALB:

```bash
# Create ALB (in public subnets)
aws elbv2 create-load-balancer \
  --name smartroute-alb \
  --subnets subnet-xxxxx subnet-yyyyy \
  --security-groups sg-xxxxx \
  --scheme internet-facing \
  --type application \
  --region ${AWS_REGION}

# Get ALB ARN from output, then create target group
aws elbv2 create-target-group \
  --name smartroute-api-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id vpc-xxxxx \
  --health-check-protocol HTTP \
  --health-check-path /health/ready \
  --health-check-interval-seconds 30 \
  --health-check-timeout-seconds 5 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --matcher HttpCode=200 \
  --region ${AWS_REGION}

# Create listener on ALB (port 443 HTTPS)
aws elbv2 create-listener \
  --load-balancer-arn <alb-arn> \
  --protocol HTTPS \
  --port 443 \
  --certificate-arn <ssl-cert-arn> \
  --default-actions Type=forward,TargetGroupArn=<target-group-arn> \
  --region ${AWS_REGION}
```

---

## Configuration & Secrets

### Task Definition Template Variables

The task definition files have placeholder variables to replace:

```json
${AWS_ACCOUNT_ID}        // e.g., 123456789012
${AWS_REGION}            // e.g., us-east-1
${DOCKERHUB_USERNAME}    // e.g., youruser
${TASK_EXECUTION_ROLE_ARN}  // e.g., arn:aws:iam::123456789012:role/ecsTaskExecutionRole-smartrouteai
${ALB_TARGET_GROUP_ARN}  // e.g., arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/smartroute-api-tg/abc123
${DOCKER_AUTH_ARN}       // Secrets Manager ARN for Docker Hub creds
```

### Steps to Configure

1. **Edit task definitions** to replace all `${...}` placeholders with actual values

2. **Verify Secrets Manager ARNs** match the secrets you created:
   ```bash
   aws secretsmanager describe-secret \
     --secret-id smartrouteai/production/database-url \
     --region ${AWS_REGION}
   ```

3. **Set environment variables** in task definition (non-sensitive only):
   ```json
   {
     "name": "ALLOWED_ORIGINS",
     "value": "https://yourdomain.com"
   },
   {
     "name": "APP_ENV",
     "value": "production"
   },
   {
     "name": "LOG_LEVEL",
     "value": "INFO"
   },
   {
     "name": "STADIA_API_KEY",
     "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789012:secret:smartrouteai/production/stadia-api-key"
   }
   ```

---

## Task Definition Deployment

### Register API Task Definition

```bash
aws ecs register-task-definition \
  --cli-input-json file://api-task-definition.json \
  --region ${AWS_REGION}
```

### Create API Service in ECS

```bash
aws ecs create-service \
  --cluster smartroute-prod \
  --service-name smartroute-api \
  --task-definition smartroute-api:1 \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxx,subnet-yyyyy],securityGroups=[sg-xxxxx],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=<tg-arn>,containerName=smartroute-api,containerPort=8000" \
  --region ${AWS_REGION}
```

### Register Worker Task Definition

```bash
aws ecs register-task-definition \
  --cli-input-json file://worker-task-definition.json \
  --region ${AWS_REGION}
```

### Create Worker Service in ECS

```bash
aws ecs create-service \
  --cluster smartroute-prod \
  --service-name smartroute-worker \
  --task-definition smartroute-worker:1 \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxx],securityGroups=[sg-xxxxx]}" \
  --region ${AWS_REGION}
```

### Verify Services

```bash
# Check API service
aws ecs describe-services \
  --cluster smartroute-prod \
  --services smartroute-api \
  --region ${AWS_REGION}

# Check Worker service
aws ecs describe-services \
  --cluster smartroute-prod \
  --services smartroute-worker \
  --region ${AWS_REGION}

# List tasks
aws ecs list-tasks \
  --cluster smartroute-prod \
  --region ${AWS_REGION}
```

---

## Monitoring & Troubleshooting

### View Logs

```bash
# API logs
aws logs tail /ecs/smartroute-api --follow --region ${AWS_REGION}

# Worker logs
aws logs tail /ecs/smartroute-worker --follow --region ${AWS_REGION}

# View logs for specific task
aws logs tail /ecs/smartroute-api --follow --log-stream-names 'ecs/smartroute-api/<task-id>' --region ${AWS_REGION}
```

### Common Issues

**Task fails to start with "CannotPullContainerImage":**
- Docker Hub credentials not found in Secrets Manager
- Docker Hub image doesn't exist or access denied
- Check IAM role permissions and Secrets Manager ARN

**Task health check fails (unhealthy):**
- Application is crashing: check logs
- `/health/ready` endpoint not responding: verify FastAPI is running
- Database connection failing: check DATABASE_URL in Secrets Manager

**Task keeps stopping and restarting:**
- Check CloudWatch logs for exceptions
- Verify all required environment variables are set
- Confirm database is accessible from ECS VPC

**WebSocket connections drop after 60 seconds:**
- ALB has idle timeout; increase it:
  ```bash
  aws elbv2 modify-load-balancer-attributes \
    --load-balancer-arn <alb-arn> \
    --attributes Key=idle_timeout.connection_termination.enabled,Value=true Key=idle_timeout.timeout_seconds,Value=3600
  ```

### Auto-Scaling (Optional)

Set up auto-scaling for the API service:

```bash
# Create auto-scaling target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/smartroute-prod/smartroute-api \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 10 \
  --region ${AWS_REGION}

# Create scaling policy (scale up when CPU > 70%)
aws application-autoscaling put-scaling-policy \
  --policy-name smartroute-api-scale-up \
  --service-namespace ecs \
  --resource-id service/smartroute-prod/smartroute-api \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 70.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    }
  }' \
  --region ${AWS_REGION}
```

---

## Updating & Rollback

### Deploy a New Version

1. **Build and push new Docker image:**
   ```bash
   docker build -t smartrouteai:v2.0 .
   docker tag smartrouteai:v2.0 ${DOCKERHUB_USERNAME}/smartrouteai:v2.0
   docker push ${DOCKERHUB_USERNAME}/smartrouteai:v2.0
   ```

2. **Register new task definition:**
   - Update task definition JSON to point to new image tag
   ```bash
   aws ecs register-task-definition \
     --cli-input-json file://api-task-definition.json \
     --region ${AWS_REGION}
   ```

3. **Update service to use new task definition:**
   ```bash
   aws ecs update-service \
     --cluster smartroute-prod \
     --service smartroute-api \
     --task-definition smartroute-api:2 \
     --region ${AWS_REGION}
   ```

4. **Monitor rollout:**
   ```bash
   watch 'aws ecs describe-services --cluster smartroute-prod --services smartroute-api --region ${AWS_REGION} | grep runningCount'
   ```

### Rollback to Previous Version

```bash
# List available task definition revisions
aws ecs describe-task-definition \
  --task-definition smartroute-api \
  --region ${AWS_REGION}

# Update service to use previous version
aws ecs update-service \
  --cluster smartroute-prod \
  --service smartroute-api \
  --task-definition smartroute-api:1 \
  --region ${AWS_REGION}
```

---

## Database Migrations

Run migrations before or after deploying a new version:

```bash
# Run one-off task to execute migrations
aws ecs run-task \
  --cluster smartroute-prod \
  --task-definition smartroute-api \
  --overrides '{
    "containerOverrides": [
      {
        "name": "smartroute-api",
        "command": ["alembic", "upgrade", "head"]
      }
    ]
  }' \
  --launch-type FARGATE \
  --network-configuration 'awsvpcConfiguration={subnets=[subnet-xxxxx],securityGroups=[sg-xxxxx]}' \
  --region ${AWS_REGION}

# Check task status
aws ecs describe-tasks \
  --cluster smartroute-prod \
  --tasks <task-arn> \
  --region ${AWS_REGION}
```

---

## Security Best Practices

✅ **Do:**
- Rotate secrets regularly in Secrets Manager
- Use least-privilege IAM roles (don't give ECS full admin access)
- Keep database credentials in Secrets Manager, not in task definition JSON
- Use HTTPS/TLS for ALB listener (port 443)
- Enable CloudWatch detailed monitoring and set alarms for error rates
- Keep Docker image base layer updated (security patches)

❌ **Don't:**
- Commit `.env` files or task definitions with real secrets
- Use public ECR repositories for private code
- Expose database publicly (use VPC security groups)
- Mix development and production Secrets Manager secrets
- Disable health checks to speed up deployment

---

## Useful AWS References

- [ECS Fargate Launch Type](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/launch_types.html)
- [ECS Task Definition Parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
- [ECS Secrets Manager Integration](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_IAM_role.html#taskexecution-role)
- [Application Load Balancer Health Checks](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html)
- [CloudWatch Container Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/ContainerInsights.html)
   and `secretsmanager:GetSecretValue` permissions.

5. Register the API and worker task definitions after replacing placeholders:

   ```bash
   aws ecs register-task-definition --cli-input-json file://api-task-definition.json
   aws ecs register-task-definition --cli-input-json file://worker-task-definition.json
   ```

6. Create or update two ECS services in the same cluster. The API service
   should use the ALB target group; the worker service should use desired count
   `1` and no load balancer.

7. Run the migration as a one-off task using the same image and environment:

   ```bash
   alembic upgrade head
   ```

   Run this before increasing the API service desired count.

8. Configure CloudWatch alarms for task count, unhealthy ALB targets, CPU,
   memory, 5xx responses, and worker task stops. ECS task health checks are
   defined in both task definitions.

Private Docker Hub credentials and application secret values are retrieved by
ECS at container start; deploy new task
revisions after rotating a secret. Never use `env_file: ./backend/.env` in the
ECS service definition.
