
# Paystub Lambda Bot

This AWS Lambda container function logs in to Viewpoint, downloads the latest pay‑stub for one employee and emails the PDF.

---

## 1 · Prerequisites

| Tool | Version |
|------|---------|
| Docker | 20.10+ |
| AWS CLI v2 | configured with permissions for **ECR** & **Lambda** |

---

## 2 · Build the container image

```bash
git clone git@github.com:sguidia/paystub-lambda.git
cd paystub-lambda
docker build -t paystub-lambda:latest .
```

---

## 3 · Publish to Amazon ECR

```bash
AWS_ACCOUNT_ID=123456789012
AWS_REGION=us‑east‑1
REPO_NAME=paystub-lambda

# Create the repo once
aws ecr create-repository \
  --repository-name "$REPO_NAME" \
  --image-scanning-configuration scanOnPush=true \
  --region "$AWS_REGION"

# Login Docker to ECR
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin \
  "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

# Tag & push
docker tag paystub-lambda:latest \
  "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO_NAME:latest"

docker push \
  "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO_NAME:latest"
```

---

## 4 · Create the Lambda function

| Setting | Value |
|---------|-------|
| **Image URI** | `AWS_ACCOUNT_ID.dkr.ecr.us‑east‑1.amazonaws.com/paystub-lambda:latest` |
| **Memory** | 1024 MB |
| **Timeout** | 300 s |
| **Architecture** | x86_64 |
| **VPC** | *leave empty unless Internet‑egress is restricted* |
---

## 5 · Environment variables

Open **Configuration → Environment variables** and add this key:

| Key | Value |
|-----|-------|
| **USERS_JSON** | `[{"username":"number","password":"password","email_to":"your_email","email_from":"your_email","email_pass":"password for app"}]` |
---


**USERS_JSON** must be pasted as a single line including the enclosing square brackets.

---

## 6 · Local smoke test (optional)

```bash
docker run --rm -p 9000:8080 \
  -e AWS_REGION=us-east-1 \
  -e USERS_JSON='[{"username":"","password":"","email_to":"","email_from":"","email_pass":""}]' \
  paystub-lambda:latest
```

And for testing run command:
```bash
curl -X POST "http://localhost:9000/2015-03-31/functions/function/invocations" \
     -d '{}'
```

---

## 7 · Invocation

Trigger the function manually from the Lambda console or attach any EventBridge schedule later if needed.

---

*Happy automating!* 🚀