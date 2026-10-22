import { Component, type ReactNode } from "react";

interface Props {
  label: string;
  children: ReactNode;
}

/** Keeps one failing panel from blanking the whole dashboard mid-demo. */
export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-red-300">
        <div>
          {this.props.label} failed: {this.state.error.message}
          <button className="btn mt-3 block w-full bg-slate-700" onClick={() => this.setState({ error: null })}>
            Retry
          </button>
        </div>
      </div>
    );
  }
}
