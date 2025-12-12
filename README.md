# 🎬 AI Demo Builder

> Automated video generation platform that uses AI to analyze GitHub repositories and generate professional demo videos.

**CS 6620 - Cloud Computing Final Project**  
**Built in 18 days** | **18 Microservices** | **$0 Budget (AWS Free Tier)**

---

## 🌟 Project Overview

AI Demo Builder is a fully automated video generation platform that:

1. **Analyzes** any GitHub repository using AI
2. **Generates** intelligent demo suggestions with Google Gemini
3. **Guides** users to record short video clips
4. **Stitches** videos together with professional transition slides
5. **Optimizes** final demo in multiple resolutions (720p, 1080p)
6. **Delivers** a shareable demo video link

### **Key Features**

- ✨ AI-powered demo suggestions using Google Gemini
- 🎥 Automated video validation and format conversion
- 🎨 Auto-generated transition slides
- ⚡ Real-time processing status updates
- 📊 Multiple resolution outputs (720p, 1080p)
- 🔔 Notification system
- 🧹 Automatic cleanup after 30 days
- 💰 Runs on AWS Free Tier

---

## 🏗️ Architecture

### **Microservices Architecture (18 Services)**

**Person 1 - Analysis Pipeline (Services 1-4):**
- Service 1: GitHub Fetcher
- Service 2: README Parser
- Service 3: Project Analyzer
- Service 4: Cache Service (with commit SHA invalidation)

**Person 2 - AI & Session Management (Services 5-6):**
- Service 5: AI Suggestion Service (Google Gemini)
- Service 6: Session Creator

**Person 3 - Upload Pipeline (Services 7-10):**
- Service 7: Upload URL Generator
- Service 8: Upload Tracker
- Service 9: Video Validator (FFmpeg)
- Service 10: Format Converter (1920x1080@30fps)

**Person 4 - Video Processing (Services 11-14):**
- Service 11: Job Queue Service
- Service 12: Slide Creator (PIL/Pillow)
- Service 13: Video Stitcher (FFmpeg concat)
- Service 14: Video Optimizer (multi-resolution)

**Person 5 - Support Services (Services 15-17):**
- Service 15: Notification Service (CloudWatch, HTTP, SNS)
- Service 16: Status Tracker (real-time progress)
- Service 17: Cleanup Service (automated 30-day cleanup)

### **AWS Resources**

| Resource | Purpose | Configuration |
|----------|---------|---------------|
| **S3** | Video storage | `ai-demo-builder` |
| **DynamoDB** | Session state & caching | `ai-demo-sessions`, `ai-demo-cache` |
| **Lambda** | 18 microservices | Python 3.11, up to 15min timeout |
| **API Gateway** | REST API | CORS enabled |
| **SQS** | Job queue | 900s visibility timeout |
| **SNS** | Notifications | Email/webhook support |
| **CloudWatch Events** | Daily cleanup | Runs at 2 AM UTC |
| **FFmpeg Layer** | Video processing | Custom Lambda layer |

---

## 📋 Prerequisites

### **Required:**
- AWS Account with CLI configured
- Python 3.11+
- Node.js 18+ (for frontend)
- AWS CDK installed: `npm install -g aws-cdk`

### **API Keys:**
- GitHub Personal Access Token (for repo analysis)
- Google Gemini API Key (for AI suggestions)

---

## 🚀 Quick Start

### **1. Clone and Setup**
```bash
# Clone repository
git clone <your-repo-url>
cd ai-demo-builder

# Create Python virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate.bat

# Install CDK dependencies
pip install -r requirements.txt
```

### **2. Setup FFmpeg Layer**
```bash
# Download and extract FFmpeg binaries
mkdir -p layers/ffmpeg/python/bin
cd layers/ffmpeg/python/bin

# Download static FFmpeg build for Lambda
wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar -xf ffmpeg-release-amd64-static.tar.xz
mv ffmpeg-*-amd64-static/ffmpeg .
mv ffmpeg-*-amd64-static/ffprobe .
chmod +x ffmpeg ffprobe
rm -rf ffmpeg-*-amd64-static*

cd ../../../..
```

### **3. Install Lambda Dependencies**
```bash
# Install dependencies for each service
for req in $(find lambda -name "requirements.txt"); do
    dir=$(dirname "$req")
    echo "Installing dependencies for $dir"
    pip install -r "$req" -t "$dir" --upgrade
done
```

### **4. Deploy Backend**
```bash
# Bootstrap CDK (first time only)
cdk bootstrap aws://$(aws sts get-caller-identity --query Account --output text)/us-west-2

# Synthesize CloudFormation template
cdk synth

# Deploy stack (takes 10-15 minutes)
cdk deploy

# Save the API endpoint from outputs!
```

### **5. Configure API Keys**
```bash
# Set GitHub token
aws lambda update-function-configuration \
  --function-name service-1-github-fetcher \
  --environment Variables="{GITHUB_TOKEN=ghp_your_token_here}"

# Set Gemini API key
aws lambda update-function-configuration \
  --function-name service-5-ai-suggestion \
  --environment Variables="{GEMINI_API_KEY=your_gemini_key_here}"
```

### **6. Setup and Run Frontend**
```bash
cd frontend

# Install dependencies
npm install

# Create .env file with your API endpoint
echo "VITE_API_BASE_URL=https://YOUR-API-ID.execute-api.us-west-2.amazonaws.com/prod" > .env

# Run development server
npm run dev

# Open http://localhost:5173
```

---

## 📁 Project Structure
ai-demo-builder/
├── ai_demo_builder/
│   ├── init.py
│   └── ai_demo_builder_stack.py      # CDK infrastructure definition
│
├── lambda/                            # All 18 microservices
│   ├── analysis/                      # Services 1-4
│   │   ├── service-1-github-fetcher/
│   │   ├── service-2-readme-parser/
│   │   ├── service-3-project-analyzer/
│   │   └── service-4-cache-service/
│   │
│   ├── ai/                            # Services 5-6
│   │   ├── service-5-ai-suggestion/
│   │   └── service-6-session-creator/
│   │
│   ├── upload/                        # Services 7-10
│   │   ├── service-7-upload-url-generator/
│   │   ├── service-8-upload-tracker/
│   │   ├── service-9-video-validator/
│   │   └── service-10-format-converter/
│   │
│   ├── processing/                    # Services 11-14
│   │   ├── service-11-job-queue/
│   │   ├── service-12-slide-creator/
│   │   ├── service-13-video-stitcher/
│   │   └── service-14-video-optimizer/
│   │
│   └── support/                       # Services 15-17
│       ├── service-15-notification/
│       ├── service-16-status-tracker/
│       └── service-17-cleanup/
│
├── layers/
│   └── ffmpeg/                        # FFmpeg binaries for video processing
│       └── python/bin/
│           ├── ffmpeg
│           └── ffprobe
│
├── frontend/                          # React + Vite frontend
│   ├── src/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
│
├── app.py                             # CDK app entry point
├── cdk.json                           # CDK configuration
├── requirements.txt                   # Python dependencies
├── requirements-dev.txt               # Development dependencies
└── README.md                          # This file

---

## 🌐 API Endpoints

**Base URL:** `https://[API-ID].execute-api.us-west-2.amazonaws.com/prod`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/suggestions` | Analyze GitHub repo and get AI suggestions |
| POST | `/upload-url` | Get presigned S3 URL for video upload |
| GET | `/status/{session_id}` | Get real-time processing status |
| POST | `/generate/{session_id}` | Trigger video generation |

### **Example Usage:**
```bash
# 1. Get AI suggestions
curl -X POST https://YOUR-API.execute-api.us-west-2.amazonaws.com/prod/suggestions \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/facebook/react"}'

# 2. Check status
curl https://YOUR-API.execute-api.us-west-2.amazonaws.com/prod/status/abc123

# 3. Generate demo
curl -X POST https://YOUR-API.execute-api.us-west-2.amazonaws.com/prod/generate/abc123
```

---

## 🔄 Complete User Flow

User submits GitHub URL
↓
Service 1-4: Analyze repository (GitHub API + caching)
↓
Service 5: Generate AI suggestions (Google Gemini)
↓
Service 6: Create session in DynamoDB
↓
User uploads 3-5 short video clips
↓
Service 7-10: Track, validate, convert videos
↓
Service 11: Queue processing job (SQS)
↓
Service 12: Generate transition slides (PIL)
↓
Service 13: Stitch videos + slides (FFmpeg)
↓
Service 14: Optimize (720p, 1080p, thumbnail)
↓
Service 15: Send notification
↓
User downloads final demo! 🎉


---

## 🎯 Key Design Decisions

### **Why Microservices?**
- Each service has single responsibility
- Independent scaling and deployment
- Easier debugging and maintenance
- Team members can work independently

### **Why Lambda?**
- Pay only for execution time (cost-effective)
- Auto-scaling to zero
- No server management
- Perfect for event-driven architecture

### **Why DynamoDB?**
- Serverless (no provisioning)
- TTL for automatic session cleanup
- Fast key-value lookups
- Pay-per-request pricing

### **Smart Caching Strategy**
- Cache key includes commit SHA
- Automatically invalidates when repo changes
- Reduces GitHub API calls
- Faster response times

### **Cost Optimization**
- Service 17: Deletes old files after 30 days
- Intermediate file cleanup saves 70% storage
- DynamoDB TTL for auto session cleanup
- Expected cost: $1-5/month with cleanup

---

## 💰 Cost Breakdown

**AWS Free Tier Coverage:**
- Lambda: 1M requests/month, 400,000 GB-seconds
- S3: 5GB storage, 20,000 GET requests
- DynamoDB: 25GB storage, 200M requests
- API Gateway: 1M API calls/month

**Expected Monthly Cost (after free tier):**
- Light usage (10-50 demos): $1-5
- Moderate usage (100-200 demos): $10-20
- Heavy usage (500+ demos): $50-100

**Cost Optimization Strategies:**
- Automatic 30-day cleanup (Service 17)
- Intermediate file deletion (70% savings)
- DynamoDB on-demand pricing
- S3 lifecycle policies

---

## 📊 System Design Highlights

### **Scalability**
- Auto-scaling Lambda functions (0 to 1000s)
- DynamoDB auto-scales to any request volume
- S3 handles unlimited storage
- SQS buffers during traffic spikes

### **Reliability**
- Retry logic in all service-to-service calls
- Dead letter queues for failed jobs
- Comprehensive error logging (CloudWatch)
- Graceful degradation (non-critical failures don't stop pipeline)

### **Performance**
- Smart caching reduces latency (Service 4)
- Parallel video processing
- FFmpeg optimization for fast encoding
- CloudFront CDN for frontend (optional)

### **Security**
- IAM roles with least-privilege access
- API keys in environment variables (not code)
- Presigned URLs for temporary S3 access
- CORS properly configured

---

## 🧪 Testing
```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run with coverage
pytest --cov=lambda tests/

# Test specific service
pytest tests/test_service_1.py -v
```

---

## 🐛 Troubleshooting

### **Issue: Lambda timeout on video processing**
**Solution:** Services 13-14 have 15-minute timeout (already configured)

### **Issue: FFmpeg not found**
**Solution:** Ensure FFmpeg binaries are in `layers/ffmpeg/python/bin/`

### **Issue: CORS errors in frontend**
**Solution:** API Gateway CORS is configured in CDK. Check browser console for exact error.

### **Issue: Upload to S3 fails (403)**
**Solution:** Check S3 bucket CORS configuration:
```bash
aws s3api get-bucket-cors --bucket ai-demo-builder
```

### **Issue: DynamoDB throughput exceeded**
**Solution:** Already using on-demand pricing, no action needed.

---

## 🔧 Useful Commands
```bash
# CDK Commands
cdk ls              # List all stacks
cdk synth           # Synthesize CloudFormation template
cdk diff            # Compare deployed vs current code
cdk deploy          # Deploy stack
cdk destroy         # Delete all resources

# View Lambda Logs
aws logs tail /aws/lambda/service-1-github-fetcher --follow

# Check DynamoDB
aws dynamodb scan --table-name ai-demo-sessions --limit 5

# List S3 contents
aws s3 ls s3://ai-demo-builder/ --recursive --human-readable

# Frontend
cd frontend
npm run dev         # Development server
npm run build       # Production build
npm run preview     # Preview production build
```

---

## 🧹 Cleanup

To delete all AWS resources:
```bash
# 1. Empty S3 buckets
aws s3 rm s3://ai-demo-builder --recursive

# 2. Destroy CDK stack
cdk destroy

# Confirm with 'y' when prompted
```

**Note:** DynamoDB tables will be deleted automatically. Sessions expire after 30 days via TTL.

---

## 📚 Documentation

- [Architecture Diagram](./docs/architecture.png)
- [Presentation Slides](./docs/presentation.pdf)
- [Demo Video](./docs/demo.mp4)
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)

---

## 👥 Team & Contributions

**CS 6620 - Cloud Computing Final Project**  
**Timeline:** November 17 - December 5, 2024 (18 days)

### **Team Responsibilities:**

- **Person 1:** Analysis Pipeline (Services 1-4)
  - GitHub integration
  - README parsing
  - Project analysis
  - Caching with commit SHA invalidation

- **Person 2:** AI & Session Management (Services 5-6)
  - Google Gemini integration
  - AI suggestion generation
  - Session creation in DynamoDB

- **Person 3:** Upload Pipeline (Services 7-10)
  - Presigned URL generation
  - S3 event handling
  - FFmpeg video validation
  - Format standardization

- **Person 4:** Video Processing (Services 11-14)
  - SQS job queue
  - Slide generation with PIL
  - FFmpeg video stitching
  - Multi-resolution optimization

- **Person 5:** Infrastructure & Support (Services 15-17 + CDK)
  - CloudWatch/SNS notifications
  - Real-time status tracking
  - Automated cleanup
  - CDK infrastructure code
  - React frontend

---

## 🎓 Learning Outcomes

### **Cloud Computing Concepts Applied:**
- ✅ Serverless architecture (Lambda, S3, DynamoDB)
- ✅ Microservices design patterns
- ✅ Event-driven architecture (S3 events, SQS)
- ✅ Infrastructure as Code (AWS CDK)
- ✅ Auto-scaling and elasticity
- ✅ Cost optimization strategies
- ✅ Security best practices (IAM, presigned URLs)
- ✅ Monitoring and logging (CloudWatch)

### **Technical Skills:**
- Python Lambda development
- FFmpeg video processing
- React frontend development
- AWS CDK (TypeScript/Python)
- DynamoDB modeling
- S3 event handling
- API Gateway configuration
- CI/CD considerations

---

## 📄 License

Educational project for CS 6620 - Cloud Computing  
University: [Your University]  
Semester: Fall 2024

---

## 🙏 Acknowledgments

- **Professor:** [Professor Name]
- **Course:** CS 6620 - Cloud Computing
- **AWS:** Free Tier for hosting
- **Google:** Gemini API for AI suggestions
- **FFmpeg:** Video processing library
- **React Team:** Frontend framework

---

## 📞 Contact

For questions or demo requests:
- GitHub Issues: [Your Repo URL]
- Email: [Your Email]

---

**Built with ❤️ by the CS 6620 Team**

*Automated video generation, powered by AI and AWS serverless architecture.*

📝 Additional Files to Create
layers/ffmpeg/python/bin/.gitkeep
# This file keeps the directory in git
# FFmpeg binaries (ffmpeg, ffprobe) should be placed here
# These are ignored by .gitignore due to large size
frontend/.env.example
bash# API Configuration
VITE_API_BASE_URL=https://YOUR-API-ID.execute-api.us-west-2.amazonaws.com/prod

# AWS Configuration
VITE_S3_BUCKET=ai-demo-builder
VITE_AWS_REGION=us-west-2