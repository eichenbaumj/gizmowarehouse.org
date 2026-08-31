import { Link } from "react-router-dom";

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-carolina/30">
        <div className="container max-w-4xl mx-auto px-6 py-5 flex items-baseline justify-between">
          <Link to="/" className="flex items-baseline gap-2 hover:opacity-80 transition-opacity">
            <span className="font-serif font-bold text-cobalt text-xl">Gizmo Warehouse</span>
            <span className="text-steel text-sm font-sans">by Joe Eichenbaum | 17A</span>
          </Link>
        </div>
        <div className="h-px bg-carolina" />
      </header>

      <main className="flex-1 container max-w-4xl mx-auto px-6 py-10">
        {children}
      </main>

      <footer>
        <div className="h-px bg-carolina" />
        <div className="container max-w-4xl mx-auto px-6 py-6 text-sm text-steel">
          Joe Eichenbaum | <a href="https://www.17a.co" target="_blank" rel="noopener noreferrer" className="hover:text-cobalt transition-colors">17A</a>
        </div>
      </footer>
    </div>
  );
}
