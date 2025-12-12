# AI Demo Builder - Deployment Guide

## Prerequisites

- Python 3.11+
- AWS CLI configured with credentials
- AWS CDK installed: `npm install -g aws-cdk`

## Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Install Lambda function dependencies:
```bash
chmod +x install-lambda-deps.sh
./install-lambda-deps.sh
```

3. Bootstrap CDK (first time only):
```bash
cdk bootstrap aws://YOUR_ACCOUNT_ID/us-east-1
```

## Deploy

```bash
cdk deploy
```

## Test

After deployment, test the API:
```bash
curl -X POST https://YOUR_API_URL/prod/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/example/repo"}'
```

Replace `YOUR_API_URL` with the API endpoint from deployment output.

## Optional: Video Processing

To enable video processing features, install FFmpeg layer:
```bash
chmod +x setup-ffmpeg-layer.sh
./setup-ffmpeg-layer.sh
cdk deploy
```

## Cleanup

Remove all AWS resources:
```bash
cdk destroy
```

## Common Issues

**"No module named 'requests'"**
→ Run `./install-lambda-deps.sh` before deploying

**"Stack already exists"**
→ Run `cdk destroy` first, then `cdk deploy`

**"Bootstrap failed"**
→ Make sure AWS CLI is configured: `aws configure`