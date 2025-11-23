import React, { useState, useEffect } from 'react';
import { air4 } from '../services/air4Service';
import { IngestItem } from '../types';
import { UploadCloud, FileText, CheckCircle2, RefreshCw, File } from 'lucide-react';

const Ingest: React.FC = () => {
  const [isDragging, setIsDragging] = useState(false);
  const [queue, setQueue] = useState<IngestItem[]>([]);
  const [uploading, setUploading] = useState(false);

  const refreshQueue = async () => {
      const q = await air4.getIngestQueueStatus();
      setQueue(q);
  };

  useEffect(() => {
    refreshQueue();
    const interval = setInterval(refreshQueue, 2000);
    return () => clearInterval(interval);
  }, []);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setUploading(true);
      const files = Array.from(e.dataTransfer.files);
      for (const file of files) {
          await air4.uploadFile(file as File);
      }
      setUploading(false);
      refreshQueue();
    }
  };

  return (
    <div className="h-full flex flex-col p-8">
      <header className="mb-8">
        <h2 className="text-2xl font-bold text-white mb-2">Ingestion Engine</h2>
        <p className="text-slate-400 text-sm">Upload documents to the local knowledge graph.</p>
      </header>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Drop Zone */}
        <div className="lg:col-span-2 flex flex-col">
          <div 
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`flex-1 border-2 border-dashed rounded-2xl flex flex-col items-center justify-center p-10 transition-all duration-300 relative overflow-hidden ${
              isDragging || uploading
                ? 'border-air-500 bg-air-500/5' 
                : 'border-white/10 bg-white/[0.02] hover:bg-white/5'
            }`}
          >
            <div className={`p-5 rounded-full mb-4 transition-all ${isDragging || uploading ? 'bg-air-500 text-white' : 'bg-white/5 text-slate-400'}`}>
              {uploading ? <RefreshCw className="w-8 h-8 animate-spin" /> : <UploadCloud className="w-8 h-8" />}
            </div>
            <h3 className="text-lg font-bold text-white mb-2">{uploading ? 'Processing...' : 'Drop files here'}</h3>
            <p className="text-slate-500 text-center max-w-md text-xs">
              PDF, DOCX, TXT, CSV supported.
            </p>
          </div>
        </div>

        {/* Queue */}
        <div className="glass-card rounded-2xl p-6 h-full overflow-hidden flex flex-col">
             <h4 className="text-sm font-bold text-white mb-4 uppercase tracking-wider opacity-70">Queue</h4>
             <div className="flex-1 overflow-y-auto space-y-3 custom-scrollbar pr-2">
                {queue.length === 0 ? (
                    <div className="text-center py-12 text-slate-600 text-xs">Queue empty</div>
                ) : (
                    queue.map(item => (
                        <div key={item.id} className="flex items-center gap-3 bg-white/5 p-3 rounded-xl border border-white/5">
                            <File className="w-4 h-4 text-air-400" />
                            <div className="flex-1 min-w-0">
                                <div className="text-xs text-white font-medium truncate">{item.filename}</div>
                                <div className="text-[10px] text-slate-500 capitalize">{item.status}</div>
                            </div>
                            {item.status === 'indexed' ? <CheckCircle2 className="w-4 h-4 text-emerald-500" /> : <RefreshCw className="w-3 h-3 text-slate-600 animate-spin" />}
                        </div>
                    ))
                )}
             </div>
        </div>
      </div>
    </div>
  );
};

export default Ingest;