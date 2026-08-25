# Amazon ECS production deployment

These task-definition templates assume ECS Fargate, Docker Hub, an
Application Load Balancer, and one production PostgreSQL database. Replace the
`${...}` placeholders before registering the task definitions. Do not commit
the rendered files or any secret values.

## Services

- `smartroute-api` runs `uvicorn main:app` on port 8000 and is attached to the
  ALB. Configure the target group health check as `GET /health/ready`.
- `smartroute-worker` runs `python worker.py` and must have one running task.
  It has no public listener and owns all scheduled jobs.

## One-time AWS setup

1. Create a private Docker Hub repository named `smartrouteai`, then push the image:

   ```bash
   docker build -t smartrouteai .
   docker login
   docker tag smartrouteai:latest ${DOCKERHUB_USERNAME}/smartrouteai:${IMAGE_TAG}
   docker push ${DOCKERHUB_USERNAME}/smartrouteai:${IMAGE_TAG}
   ```

2. Create Secrets Manager secrets named:

   - `smartrouteai/production/database-url`
   - `smartrouteai/production/clerk-jwks-url`
   - `smartrouteai/production/clerk-issuer`
   - `smartrouteai/production/dockerhub-credentials`

   Store Docker Hub credentials as JSON with a least-privilege access token:

   ```json
   {"username":"your-dockerhub-user","password":"your-dockerhub-access-token"}
   ```

   Keep `ALLOWED_ORIGINS` and other non-sensitive deployment settings in the
   task definition or your deployment parameter store.

3. Create the CloudWatch log groups before registering the task definitions:

   ```bash
   aws logs create-log-group --log-group-name /ecs/smartroute-api --region ${AWS_REGION}
   aws logs create-log-group --log-group-name /ecs/smartroute-worker --region ${AWS_REGION}
   ```

4. Attach [ecs-task-execution-secrets-policy.json](./ecs-task-execution-secrets-policy.json)
   to the ECS task execution role. The execution role needs CloudWatch Logs
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
