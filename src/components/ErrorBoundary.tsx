import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
    this.handleReset = this.handleReset.bind(this);
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  handleReset() {
    this.setState({ hasError: false, error: null });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-[60vh] bg-background flex items-center justify-center p-8">
          <div className="bg-surface-container rounded-2xl border border-outline-variant/20 p-12 max-w-lg w-full text-center space-y-6">
            <div className="w-16 h-16 rounded-full bg-error/10 flex items-center justify-center mx-auto">
              <AlertTriangle size={32} className="text-error" />
            </div>
            <div className="space-y-2">
              <h1 className="font-headline text-2xl font-bold text-on-surface uppercase tracking-tight">
                Something Went Wrong
              </h1>
              <p className="text-sm text-on-surface-variant leading-relaxed">
                An unexpected error occurred in the synthesis engine. You can try resetting the current view.
              </p>
            </div>
            {this.state.error && (
              <div className="bg-surface-container-lowest rounded-lg p-4 text-left">
                <p className="font-mono text-[11px] text-error/80 break-all">
                  {this.state.error.message}
                </p>
              </div>
            )}
            <button
              onClick={this.handleReset}
              className="inline-flex items-center gap-2 bg-primary text-on-primary px-8 py-3 rounded-lg font-bold uppercase tracking-widest text-xs hover:bg-primary-container transition-all active:scale-[0.98]"
            >
              <RotateCcw size={14} />
              Reset View
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
