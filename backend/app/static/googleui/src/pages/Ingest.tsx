
import React, { useState, useEffect, useRef } from 'react';
import { air4 } from '../services/air4Service';
import { IngestItem } from '../types';
import { UploadCloud, FileText, CheckCircle2, RefreshCw, File, AlertCircle, XCircle, CheckCircle, Loader2 } from 'lucide-react';

const Ingest: React.FC = () => {
  const [isDragging, setIsDragging] = useState(false);
  const [queue, setQueue] = useState<IngestItem[]>([]);
  const [activeUploads, setActiveUploads] = useState<{id: string, name: string, size: number, progress: number}[]>([]);
  const [notification, setNotification] = useState<{type: 'success' | 'error', message: string} | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refreshQueue = async () => {
      const q = await air4.getIngestQueueStatus();
      setQueue(q);
  };

  useEffect(() => {
    refreshQueue();
    const interval = setInterval(refreshQueue, 1000); // Faster polling for smoother "real-time" feel
    return () => clearInterval(interval);
  }, []);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const formatBytes = (bytes: number, decimals = 2) => {
      if (bytes === 0) return '0 Bytes';
      const k = 1024;
      const dm = decimals < 0 ? 0 : decimals;
      const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  };

  const processFiles = async (files: File[]) => {
      setNotification(null);
      
      let success = 0;
      let failed = 0;

      // Add to local upload queue
      const newUploads = files.map(f => ({
          id: Math.random().toString(36).substring(7),
          name: f.name,
          size: f.size,
          progress: 0
      }));
      
      setActiveUploads(prev => [...prev, ...newUploads]);

      for (let i = 0; i < files.length; i++) {
          const file = files[i];
          const uploadId = newUploads[i].id;

          // Simulate upload progress for UI feedback since fetch doesn't give XHR progress easily
          const progressInterval = setInterval(() => {
              setActiveUploads(prev => prev.map(u => 
                  u.id === uploadId ? { ...u, progress: Math.min(u.progress + 10, 90) } : u
              ));
          }, 100);

          const ok = await air4.uploadFile(file);
          
          clearInterval(progressInterval);
          
          // Remove from local uploads
          setActiveUploads(prev => prev.filter(u => u.id !== uploadId));
          
          if (ok) success++;
          else failed++;
      }
      
      refreshQueue();

      if (failed === 0 && success > 0) {
          setNotification({ type: 'success', message: `Successfully queued ${success} file(s) for ingestion.` });
      } else if (success > 0 && failed > 0) {
          setNotification({ type: 'error', message: `Queued ${success} files, but ${failed} failed.` });
      } else if (failed > 0) {
          setNotification({ type: 'error', message: `Failed to upload ${failed} file(s). System may be offline.` });
      }
      
      setTimeout(() => setNotification(null), 5000);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      await processFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleZoneClick = () => {
      fileInputRef.current?.click();
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
          await processFiles(Array.from(e.target.files));
      }
      if (fileInputRef.current) {
          fileInputRef.current.value = '';
      }
  };

  const isUploading = activeUploads.length > 0;

  return (
    <div className="h-full flex flex-col p-8 relative">
      <header className="mb-8">
        <h2 className="text-2xl font-bold text-white mb-2">Ingestion Engine</h2>
        <p className="text-slate-400 text-sm">Upload documents to the local knowledge graph.</p>
      </header>

      {/* Notification Toast */}
      {notification && (
          <div className={`absolute top-8 right-8 px-4 py-3 rounded-xl flex items-center gap-3 shadow-2xl animate-in slide-in-from-top-4 fade-in duration-300 z-50 ${
              notification.type === 'success' ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400' : 'bg-red-500/10 border border-red-500/20 text-red-400'
          }`}>
              {notification.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
              <span className="text-sm font-medium">{notification.message}</span>
          </div>
      )}

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-6 min-h-0">
        {/* Drop Zone */}
        <div className="lg:col-span-2 flex flex-col h-full">
          <input 
              type="file" 
              multiple 
              ref={fileInputRef} 
              className="hidden" 
              onChange={handleFileSelect}
              accept=".pdf,.txt,.docx,.csv,.md" 
          />
          <div 
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={handleZoneClick}
            className={`flex-1 border-2 border-dashed rounded-2xl flex flex-col items-center justify-center p-10 transition-all duration-300 relative overflow-hidden cursor-pointer group ${
              isDragging || isUploading
                ? 'border-air-500 bg-air-500/5' 
                : 'border-white/10 bg-white/[0.02] hover:bg-white/5 hover:border-air-500/30'
            }`}
          >
            <div className={`p-5 rounded-full mb-4 transition-all ${isDragging || isUploading ? 'bg-air-500 text-white' : 'bg-white/5 text-slate-400 group-hover:text-air-400 group-hover:bg-air-500/10'}`}>
              {isUploading ? <RefreshCw className="w-8 h-8 animate-spin" /> : <UploadCloud className="w-8 h-8" />}
            </div>
            <h3 className="text-lg font-bold text-white mb-2">{isUploading ? 'Uploading Files...' : 'Drop files here'}</h3>
            <p className="text-slate-500 text-center max-w-md text-xs mb-4">
              or click to browse
            </p>
            <p className="text-slate-600 text-center text-[10px] bg-white/5 px-3 py-1 rounded-full">
              Supported: PDF, DOCX, TXT, CSV, MD
            </p>
          </div>
        </div>

        {/* Queue Monitor */}
        <div className="glass-card rounded-2xl p-6 h-full flex flex-col border border-white/5">
             <div className="flex items-center justify-between mb-4 flex-shrink-0">
                <h4 className="text-sm font-bold text-white uppercase tracking-wider opacity-70">Activity Monitor</h4>
                <div className="flex items-center gap-2">
                     <span className={`w-2 h-2 rounded-full ${(activeUploads.length > 0 || queue.some(i => i.status === 'processing')) ? 'bg-air-500 animate-pulse' : 'bg-slate-700'}`}></span>
                     <span className="text-[10px] text-slate-500">Live</span>
                </div>
             </div>
             
             <div className="flex-1 overflow-y-auto space-y-3 custom-scrollbar pr-2 min-h-0">
                {(activeUploads.length === 0 && queue.length === 0) ? (
                    <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-3">
                        <div className="p-4 rounded-full bg-white/5">
                            <FileText className="w-8 h-8 opacity-20" />
                        </div>
                        <span className="text-xs">No active tasks</span>
                    </div>
                ) : (
                    <>
                        {/* Active Uploads */}
                        {activeUploads.map(item => (
                            <QueueItem 
                                key={item.id}
                                name={item.name}
                                size={item.size}
                                status="uploading"
                                progress={item.progress}
                            />
                        ))}

                        {/* Backend Queue */}
                        {queue.map(item => (
                            <QueueItem 
                                key={item.id}
                                name={item.filename}
                                size={item.size}
                                status={item.status}
                                progress={item.progress}
                            />
                        ))}
                    </>
                )}
             </div>
        </div>
      </div>
    </div>
  );
};

// Extracted Queue Item Component for consistent styling
const QueueItem: React.FC<{ name: string; size: number; status: string; progress: number }> = ({ name, size, status, progress }) => {
    let statusColor = 'text-slate-400';
    let statusText = 'Unknown';
    let barColor = 'bg-air-500';
    let icon = <Loader2 className="w-4 h-4 text-slate-400 animate-spin" />;

    switch(status) {
        case 'uploading':
            statusColor = 'text-blue-400';
            statusText = 'Uploading...';
            barColor = 'bg-blue-500';
            icon = <UploadCloud className="w-4 h-4 text-blue-400 animate-pulse" />;
            break;
        case 'processing':
        case 'queued':
            statusColor = 'text-air-400';
            statusText = status === 'queued' ? 'Queued' : `Processing ${progress.toFixed(0)}%`;
            barColor = 'bg-air-500';
            icon = <RefreshCw className="w-4 h-4 text-air-400 animate-spin" />;
            break;
        case 'indexed':
            statusColor = 'text-emerald-400';
            statusText = 'Ingestion Complete';
            barColor = 'bg-emerald-500';
            icon = <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
            break;
        case 'error':
            statusColor = 'text-red-400';
            statusText = 'Failed';
            barColor = 'bg-red-500';
            icon = <AlertCircle className="w-4 h-4 text-red-500" />;
            break;
    }

    const formatBytes = (bytes: number) => {
        if (!bytes) return '';
        const k = 1024;
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + ['B', 'KB', 'MB', 'GB'][i];
    };

    return (
        <div className="bg-white/5 p-3 rounded-xl border border-white/5 animate-in slide-in-from-right-2 fade-in duration-300">
            <div className="flex items-start gap-3">
                <div className={`p-2 rounded-lg bg-white/5 flex-shrink-0`}>
                    {icon}
                </div>
                <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-start mb-1">
                        <div className="text-xs text-white font-medium truncate pr-2" title={name}>{name}</div>
                        {size > 0 && <div className="text-[10px] text-slate-500 font-mono whitespace-nowrap">{formatBytes(size)}</div>}
                    </div>
                    
                    {/* Progress Bar Container */}
                    <div className="h-1.5 w-full bg-white/10 rounded-full overflow-hidden mb-1.5 relative">
                        <div 
                            className={`h-full rounded-full transition-all duration-500 ${barColor} ${status === 'processing' || status === 'uploading' ? 'progress-stripe' : ''}`} 
                            style={{ width: `${progress}%` }}
                        ></div>
                    </div>

                    <div className={`text-[10px] font-medium ${statusColor}`}>
                        {statusText}
                    </div>
                </div>
            </div>
            <style>{`
                .progress-stripe {
                    background-image: linear-gradient(45deg,rgba(255,255,255,.15) 25%,transparent 25%,transparent 50%,rgba(255,255,255,.15) 50%,rgba(255,255,255,.15) 75%,transparent 75%,transparent);
                    background-size: 1rem 1rem;
                    animation: progress-bar-stripes 1s linear infinite;
                }
                @keyframes progress-bar-stripes {
                    0% { background-position: 1rem 0; }
                    100% { background-position: 0 0; }
                }
            `}</style>
        </div>
    );
}

export default Ingest;
