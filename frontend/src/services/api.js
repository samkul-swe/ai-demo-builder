import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001';

// Create axios instance with default config
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30 second timeout for AI calls
});

// Add response interceptor for error handling
apiClient.interceptors.response.use(
  response => {
    // Handle Lambda response format where body might be stringified
    if (response.data && typeof response.data.body === 'string') {
      try {
        response.data.body = JSON.parse(response.data.body);
      } catch (e) {
        console.warn('Could not parse response body as JSON');
      }
    }
    return response.data;
  },
  error => {
    if (error.code === 'ECONNABORTED') {
      console.error('API Error: Request timeout');
      return Promise.reject(new Error('Request timeout - Lambda may be cold starting'));
    }

    if (error.code === 'ERR_NETWORK' || !error.response) {
      console.error('API Error: Network error - Cannot reach server');
      console.error('Check if API_URL is correct:', API_BASE_URL);
      return Promise.reject(new Error('Network Error: Cannot reach the API server. Check your API URL configuration.'));
    }
    
    const errorMessage = error.response?.data?.body?.error || 
                        error.response?.data?.error || 
                        error.message || 
                        'An error occurred';
    console.error('API Error:', errorMessage);
    return Promise.reject(new Error(errorMessage));
  }
);

const api = {
  /**
   * Step 1: Analyze GitHub repository
   * Calls Service 1 (GitHub Fetcher) which orchestrates Services 2-4
   * Returns: github_data, parsed_readme, project_analysis
   */
  async analyzeGitHub(githubUrl) {
    try {
      console.log('Analyzing GitHub repo:', githubUrl);
      const response = await apiClient.post('/analyze', { 
        github_url: githubUrl 
      });
      
      console.log('Raw analyze response:', response);
      
      // Handle nested body structure from Lambda
      let data = response;
      
      // If response has a body field that's a string, parse it
      if (response.body && typeof response.body === 'string') {
        try {
          data = JSON.parse(response.body);
        } catch (e) {
          console.error('Failed to parse response.body:', e);
        }
      } else if (response.body && typeof response.body === 'object') {
        data = response.body;
      }
      
      console.log('Parsed analyze data:', data);
      
      // Validate required fields
      if (!data.github_data) {
        throw new Error('Invalid response: missing github_data');
      }
      
      return data;
    } catch (error) {
      console.error('Error in analyzeGitHub:', error);
      throw error;
    }
  },

  /**
   * Step 2: Get AI video suggestions
   * Calls Service 5 (AI Suggestion Service)
   * Input: Output from analyzeGitHub (github_data, parsed_readme, project_analysis)
   * Returns: { session_id, videos[], total_suggestions, project_name, etc. }
   */
  async getSuggestions(analysisData) {
    try {
      console.log('Getting AI suggestions with data:', analysisData);
      
      // Validate input
      if (!analysisData || !analysisData.github_data) {
        throw new Error('Invalid analysis data: missing github_data');
      }
      
      // Service 5 expects the full analysis object
      const response = await apiClient.post('/suggestions', analysisData);
      
      console.log('Raw suggestions response:', response);
      
      // Handle nested body structure
      let data = response;
      
      if (response.body && typeof response.body === 'string') {
        try {
          data = JSON.parse(response.body);
        } catch (e) {
          console.error('Failed to parse response.body:', e);
        }
      } else if (response.body && typeof response.body === 'object') {
        data = response.body;
      }
      
      console.log('Parsed suggestions data:', data);
      
      // Validate response has required fields
      if (!data.session_id) {
        throw new Error('Invalid response: missing session_id');
      }
      
      return {
        sessionId: data.session_id,
        projectName: data.project_name,
        owner: data.owner,
        githubUrl: data.github_url,
        suggestions: data.videos || [],
        totalSuggestions: data.total_suggestions,
        overallFlow: data.overall_flow,
        totalDuration: data.total_estimated_duration,
        tips: data.project_specific_tips || [],
        metadata: data.project_metadata || {},
        cached: data.cached || false
      };
    } catch (error) {
      console.error('Error in getSuggestions:', error);
      throw error;
    }
  },

  /**
   * Step 3: Get presigned upload URL for video
   * Calls Service 7 (Upload URL Generator)
   * Returns: { upload_url, key, expires_in }
   */
  async getUploadUrl(sessionId, suggestionId, fileName) {
    try {
      console.log(`Getting upload URL for session ${sessionId}, suggestion ${suggestionId}`);
      const response = await apiClient.post('/upload-url', {
        session_id: sessionId,
        suggestion_id: suggestionId,
        file_name: fileName
      });

      // Response format: { statusCode: 200, body: { upload_url, key, expires_in } }
      return response.body || response;
    } catch (error) {
      console.error('Error in getUploadUrl:', error);
      throw error;
    }
  },

  /**
   * Step 4: Upload video directly to S3
   * Uses presigned URL from getUploadUrl
   */
  async uploadVideo(presignedUrl, videoFile, onProgress) {
    try {
      console.log('Uploading video to S3...');
      
      await axios.put(presignedUrl, videoFile, {
        headers: {
          'Content-Type': videoFile.type,
        },
        onUploadProgress: (progressEvent) => {
          if (onProgress && progressEvent.total) {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            onProgress(percentCompleted);
          }
        },
      });
      
      console.log('Video uploaded successfully');
      return { success: true };
    } catch (error) {
      console.error('Error uploading video:', error);
      throw new Error('Failed to upload video to S3');
    }
  },

  /**
   * Step 5: Get session status
   * Calls Service 16 (Status Tracker)
   * Returns: { session_id, status, progress, videos_total, videos_uploaded, etc. }
   */
  async getSessionStatus(sessionId) {
    try {
      console.log('Getting session status:', sessionId);
      const response = await apiClient.get(`/status/${sessionId}`);
      
      // Response format: { statusCode: 200, body: { success: true, data: { ... } } }
      const body = response.body || response;
      
      // Handle both string and object body
      if (typeof body === 'string') {
        const parsed = JSON.parse(body);
        return parsed.data || parsed;
      }
      
      return body.data || body;
    } catch (error) {
      console.error('Error in getSessionStatus:', error);
      throw error;
    }
  },

  /**
   * Step 6: Trigger final video generation
   * Calls Service 11 (Job Queue Service)
   * This starts the processing pipeline (Services 12-14)
   */
  async generateFinalVideo(sessionId) {
    try {
      console.log('Triggering final video generation:', sessionId);
      const response = await apiClient.post(`/generate/${sessionId}`);
      
      // Response format: { statusCode: 200, body: { job_id, message, ... } }
      return response.body || response;
    } catch (error) {
      console.error('Error in generateFinalVideo:', error);
      throw error;
    }
  },

  /**
   * Step 7: Get final demo video URL
   * Gets the final video from session status
   */
  async getFinalVideo(sessionId) {
    try {
      console.log('Getting final video:', sessionId);
      const status = await this.getSessionStatus(sessionId);
      
      if (status.demo_url) {
        return {
          videoUrl: status.demo_url,
          thumbnailUrl: status.thumbnail_url,
          status: status.status,
        };
      }
      
      throw new Error('Final video not yet available');
    } catch (error) {
      console.error('Error in getFinalVideo:', error);
      throw error;
    }
  },

  /**
   * Utility: Poll session status until complete or timeout
   */
  async pollSessionStatus(sessionId, options = {}) {
    const {
      maxAttempts = 60,
      intervalMs = 5000,
      onProgress = null,
    } = options;

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const status = await this.getSessionStatus(sessionId);
      
      if (onProgress) {
        onProgress(status);
      }

      // Check if processing is complete
      if (status.status === 'completed') {
        return status;
      }

      // Check if there was an error
      if (status.status === 'failed' || status.status === 'error') {
        throw new Error(status.error_message || 'Video processing failed');
      }

      // Wait before next poll
      await new Promise(resolve => setTimeout(resolve, intervalMs));
    }

    throw new Error('Timeout waiting for video processing to complete');
  }
};

export default api;