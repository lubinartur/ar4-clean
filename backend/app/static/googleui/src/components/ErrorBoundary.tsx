// P2.2: Error Boundary to prevent full app crash from workspace errors
import React, { Component, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Home, Copy, ChevronDown, ChevronRight } from 'lucide-react';

interface ErrorBoundaryProps {
  children: ReactNode;
  onGoHome?: () => void;  // P2.2: Callback to navigate to safe workspace
  workspaceName?: string; // P2.2: Name of the workspace for error context
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
  detailsExpanded: boolean;
  copied: boolean;
}

// P2.2: Class component required for componentDidCatch
class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      detailsExpanded: false,
      copied: false,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    // P2.2: Update state to render fallback UI
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    // P2.2: Log error for debugging
    console.error('[P2.2 ErrorBoundary] Caught error:', error);
    console.error('[P2.2 ErrorBoundary] Component stack:', errorInfo.componentStack);
    this.setState({ errorInfo });
  }

  handleReload = (): void => {
    // P2.2: Hard reload the page
    window.location.reload();
  };

  handleGoHome = (): void => {
    // P2.2: Navigate to safe workspace and reset error state
    this.setState({ hasError: false, error: null, errorInfo: null });
    if (this.props.onGoHome) {
      this.props.onGoHome();
    }
  };

  handleCopyDetails = async (): Promise<void> => {
    // P2.2: Copy error details to clipboard
    const { error, errorInfo } = this.state;
    const details = [
      `Error: ${error?.message || 'Unknown error'}`,
      `Name: ${error?.name || 'Error'}`,
      `Workspace: ${this.props.workspaceName || 'Unknown'}`,
      `Timestamp: ${new Date().toISOString()}`,
      '',
      'Stack trace:',
      error?.stack || 'No stack trace available',
      '',
      'Component stack:',
      errorInfo?.componentStack || 'No component stack available',
    ].join('\n');

    try {
      await navigator.clipboard.writeText(details);
      this.setState({ copied: true });
      setTimeout(() => this.setState({ copied: false }), 2000);
    } catch (e) {
      console.error('[P2.2] Failed to copy to clipboard:', e);
    }
  };

  toggleDetails = (): void => {
    this.setState(prev => ({ detailsExpanded: !prev.detailsExpanded }));
  };

  render(): ReactNode {
    const { hasError, error, errorInfo, detailsExpanded, copied } = this.state;
    const { children, workspaceName } = this.props;

    if (hasError) {
      // P2.2: Fallback UI with dark theme
      return (
        <div className="h-full flex flex-col items-center justify-center p-8 bg-slate-900/50">
          <div className="max-w-lg w-full glass-card rounded-2xl p-8 border border-red-500/20 shadow-2xl">
            {/* Header */}
            <div className="flex items-center gap-4 mb-6">
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20">
                <AlertTriangle className="w-8 h-8 text-red-400" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">Something crashed</h2>
                <p className="text-sm text-slate-400">
                  {workspaceName ? `Error in ${workspaceName}` : 'An error occurred in this workspace'}
                </p>
              </div>
            </div>

            {/* Error message */}
            <div className="mb-6 p-4 bg-red-500/5 rounded-xl border border-red-500/10">
              <p className="text-sm text-red-300 font-mono break-all">
                {error?.message || 'Unknown error'}
              </p>
            </div>

            {/* Action buttons */}
            <div className="flex gap-3 mb-6">
              <button
                onClick={this.handleReload}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 rounded-xl text-white text-sm font-medium transition-all"
              >
                <RefreshCw className="w-4 h-4" />
                Reload
              </button>
              <button
                onClick={this.handleGoHome}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-air-500/20 hover:bg-air-500/30 border border-air-500/30 hover:border-air-500/50 rounded-xl text-white text-sm font-medium transition-all"
              >
                <Home className="w-4 h-4" />
                Go Home
              </button>
              <button
                onClick={this.handleCopyDetails}
                className="flex items-center justify-center gap-2 px-4 py-3 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 rounded-xl text-white text-sm font-medium transition-all"
              >
                <Copy className="w-4 h-4" />
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>

            {/* Expandable details */}
            <div className="border border-white/5 rounded-xl overflow-hidden">
              <button
                onClick={this.toggleDetails}
                className="w-full flex items-center justify-between px-4 py-3 bg-white/[0.02] hover:bg-white/5 text-slate-400 text-sm font-medium transition-colors"
              >
                <span>Technical Details</span>
                {detailsExpanded ? (
                  <ChevronDown className="w-4 h-4" />
                ) : (
                  <ChevronRight className="w-4 h-4" />
                )}
              </button>
              {detailsExpanded && (
                <div className="p-4 bg-black/20 max-h-60 overflow-auto">
                  <div className="mb-3">
                    <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Stack Trace</span>
                    <pre className="mt-1 text-xs text-slate-400 font-mono whitespace-pre-wrap break-all">
                      {error?.stack || 'No stack trace available'}
                    </pre>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Component Stack</span>
                    <pre className="mt-1 text-xs text-slate-400 font-mono whitespace-pre-wrap break-all">
                      {errorInfo?.componentStack || 'No component stack available'}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      );
    }

    return children;
  }
}

export default ErrorBoundary;
