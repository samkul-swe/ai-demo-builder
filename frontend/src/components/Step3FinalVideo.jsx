import React, { useEffect, useState } from 'react';
import { Video, Download, Share2, CheckCircle, XCircle, Loader, RotateCcw, Play } from 'lucide-react';
import LoadingSpinner from './LoadingSpinner';
import api from '../services/api';

function Step3FinalVideo({ sessionId, onStartOver }) {
  const [status, setStatus] = useState('processing');
  const [progress, setProgress] = useState(0);
  const [statusData, setStatusData] = useState(null);
  const [error, setError] = useState(null);
  const [pollingCount, setPollingCount] = useState(0);

  useEffect(() => {
    // Start polling for status
    const pollStatus = async () => {
      try {
        const statusResponse = await api.getSessionStatus(sessionId);
        console.log('Status update:', statusResponse);
        
        setStatusData(statusResponse);
        setProgress(statusResponse.progress?.percentage || 0);
        setStatus(statusResponse.status);

        // Check if processing is complete
        if (statusResponse.status === 'complete') {
          clearInterval(pollInterval);
        } else if (statusResponse.status?.includes('failed')) {
          setError(statusResponse.error?.message || 'Video processing failed');
          clearInterval(pollInterval);
        }
      } catch (err) {
        console.error('Error polling status:', err);
        setPollingCount(prev => prev + 1);
        
        // Stop polling after 60 attempts (5 minutes at 5 second intervals)
        if (pollingCount >= 60) {
          clearInterval(pollInterval);
          setError('Timeout waiting for video processing');
        }
      }
    };

    // Poll every 5 seconds
    const pollInterval = setInterval(pollStatus, 5000);
    
    // Initial poll
    pollStatus();

    return () => clearInterval(pollInterval);
  }, [sessionId, pollingCount]);

  const handleGenerateVideo = async () => {
    try {
      setStatus('queued');
      await api.generateFinalVideo(sessionId);
    } catch (err) {
      console.error('Error generating video:', err);
      setError(err.message || 'Failed to start video generation');
    }
  };

  const handleDownload = () => {
    if (statusData?.result?.demo_url) {
      const link = document.createElement('a');
      link.href = statusData.result.demo_url;
      link.download = `${statusData.project_name || 'demo'}-video.mp4`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  const handleShare = () => {
    const url = statusData?.result?.demo_url;
    if (navigator.share && url) {
      navigator.share({
        title: `${statusData.project_name} Demo Video`,
        text: 'Check out this demo video created with AI Demo Builder!',
        url: url
      }).catch(console.error);
    } else if (url) {
      navigator.clipboard.writeText(url).then(() => {
        alert('Video URL copied to clipboard!');
      });
    }
  };

  // Status is 'ready_for_processing' - show generate button
  if (status === 'ready_for_processing' || status === 'uploading') {
    return (
      <div className="max-w-3xl mx-auto text-center py-12">
        <div className="inline-flex items-center justify-center w-24 h-24 bg-gradient-to-r from-green-500 to-blue-600 rounded-full mb-6">
          <CheckCircle className="w-12 h-12 text-white" />
        </div>
        <h2 className="text-3xl font-bold text-gray-900 mb-4">
          All Videos Uploaded Successfully!
        </h2>
        <p className="text-gray-600 mb-8">
          Your {statusData?.videos?.length || 0} videos have been uploaded, validated, and converted.
          Ready to create your final demo video!
        </p>
        
        <button
          onClick={handleGenerateVideo}
          className="btn-primary flex items-center justify-center mx-auto text-lg px-8 py-4"
        >
          <Play className="w-6 h-6 mr-2" />
          Generate Final Demo Video
        </button>
      </div>
    );
  }

  // Status is processing
  if (['queued', 'slides_ready', 'stitching', 'stitched', 'optimizing'].includes(status)) {
    return (
      <div className="max-w-3xl mx-auto text-center py-12">
        <div className="inline-flex items-center justify-center w-24 h-24 bg-gradient-to-r from-blue-500 to-purple-600 rounded-full mb-6 animate-pulse">
          <Video className="w-12 h-12 text-white" />
        </div>
        <h2 className="text-3xl font-bold text-gray-900 mb-4">
          {statusData?.progress?.step || 'Processing Your Video'}
        </h2>
        <p className="text-gray-600 mb-8">
          {statusData?.progress?.message || 'Creating your professional demo video...'}
        </p>
        
        {/* Progress Bar */}
        <div className="max-w-md mx-auto mb-8">
          <div className="flex justify-between text-sm text-gray-600 mb-2">
            <span>Step {statusData?.progress?.step_number || 0} of {statusData?.progress?.total_steps || 7}</span>
            <span>{progress}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-3">
            <div
              className="bg-gradient-to-r from-blue-500 to-purple-600 h-3 rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        <LoadingSpinner size="large" />
        
        {statusData?.progress?.current_operation && (
          <p className="text-sm text-gray-500 mt-4">{statusData.progress.current_operation}</p>
        )}
        <p className="text-sm text-gray-500 mt-2">This usually takes 2-5 minutes</p>
      </div>
    );
  }

  // Status is complete
  if (status === 'complete' && statusData?.result?.demo_url) {
    return (
      <div className="max-w-3xl mx-auto py-8">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-24 h-24 bg-green-100 rounded-full mb-6">
            <CheckCircle className="w-16 h-16 text-green-600" />
          </div>
          <h2 className="text-3xl font-bold text-gray-900 mb-4">
            Your Demo Video is Ready! 🎉
          </h2>
          <p className="text-gray-600">
            {statusData.project_name} demo video created successfully
          </p>
        </div>

        {/* Video Player */}
        <div className="mb-8 rounded-lg overflow-hidden shadow-xl">
          <video
            controls
            className="w-full"
            poster={statusData.result.thumbnail_url}
            src={statusData.result.demo_url}
          >
            Your browser does not support the video tag.
          </video>
        </div>

        {/* Video Details */}
        {statusData.result.final_video_duration && (
          <div className="text-center text-sm text-gray-600 mb-6">
            Duration: {statusData.result.final_video_duration} • 
            Size: {(statusData.result.final_video_size / (1024 * 1024)).toFixed(2)} MB
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
          <button
            onClick={handleDownload}
            className="btn-primary flex items-center justify-center"
          >
            <Download className="w-5 h-5 mr-2" />
            Download Video (1080p)
          </button>
          <button
            onClick={handleShare}
            className="btn-secondary flex items-center justify-center"
          >
            <Share2 className="w-5 h-5 mr-2" />
            Share Video
          </button>
        </div>

        {/* Multiple Resolutions */}
        {statusData.result.demo_url_720p && (
          <div className="p-4 bg-gray-50 rounded-lg mb-6">
            <p className="text-sm font-semibold text-gray-700 mb-2">Available Resolutions:</p>
            <div className="flex flex-wrap gap-2">
              <a
                href={statusData.result.demo_url_720p}
                download
                className="text-sm px-3 py-1 bg-white border border-gray-300 rounded hover:bg-gray-100"
              >
                720p
              </a>
              <a
                href={statusData.result.demo_url_1080p || statusData.result.demo_url}
                download
                className="text-sm px-3 py-1 bg-white border border-gray-300 rounded hover:bg-gray-100"
              >
                1080p
              </a>
            </div>
          </div>
        )}

        {/* Video URL */}
        <div className="p-4 bg-gray-50 rounded-lg">
          <p className="text-sm text-gray-600 mb-2">Direct Link:</p>
          <div className="flex items-center space-x-2">
            <input
              type="text"
              value={statusData.result.demo_url}
              readOnly
              className="flex-1 px-3 py-2 bg-white border border-gray-300 rounded text-sm"
              onClick={(e) => e.target.select()}
            />
            <button
              onClick={() => navigator.clipboard.writeText(statusData.result.demo_url)}
              className="px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded text-sm transition-colors"
            >
              Copy
            </button>
          </div>
        </div>

        {/* Start Over Button */}
        <button
          onClick={onStartOver}
          className="btn-secondary flex items-center justify-center mx-auto mt-8"
        >
          <RotateCcw className="w-5 h-5 mr-2" />
          Create Another Demo
        </button>
      </div>
    );
  }

  // Status is failed
  if (status?.includes('failed') || error) {
    return (
      <div className="max-w-3xl mx-auto text-center py-12">
        <div className="inline-flex items-center justify-center w-24 h-24 bg-red-100 rounded-full mb-6">
          <XCircle className="w-16 h-16 text-red-600" />
        </div>
        <h2 className="text-3xl font-bold text-gray-900 mb-4">
          Processing Failed
        </h2>
        <p className="text-gray-600 mb-4">
          {error || statusData?.error?.message || 'An error occurred during video processing'}
        </p>
        <p className="text-sm text-gray-500 mb-8">
          Error at step: {statusData?.error?.step || 'unknown'}
        </p>
        
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <button
            onClick={handleGenerateVideo}
            className="btn-primary flex items-center justify-center"
          >
            <RotateCcw className="w-5 h-5 mr-2" />
            Try Again
          </button>
          <button
            onClick={onStartOver}
            className="btn-secondary flex items-center justify-center"
          >
            Start Over
          </button>
        </div>
      </div>
    );
  }

  // Default loading state
  return (
    <div className="max-w-3xl mx-auto text-center py-12">
      <LoadingSpinner size="large" />
      <p className="text-gray-600 mt-4">Loading video status...</p>
    </div>
  );
}

export default Step3FinalVideo;