export function Dashboard() {
  return (
    <div className="min-h-screen bg-gray-950 text-white flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center gap-3">
          <span className="text-2xl">🚌</span>
          <h1 className="text-xl font-bold tracking-tight">WaitWatch</h1>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 flex items-center justify-center px-6">
        <div className="max-w-lg text-center space-y-6">
          <div className="space-y-2">
            <h2 className="text-4xl font-bold tracking-tight">
              Real-Time Transit Tracking
            </h2>
            <p className="text-gray-400 text-lg">
              Know exactly when your bus or train arrives — powered by live
              vehicle data and smart predictions.
            </p>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 space-y-3">
            <div className="flex items-center gap-2 text-amber-400">
              <span className="text-sm">⚙️</span>
              <span className="text-sm font-medium">
                Setting up the foundation
              </span>
            </div>
            <p className="text-gray-500 text-sm">
              WaitWatch is currently being initialized. Route exploration, live
              tracking, and ETA predictions are coming soon.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <Feature icon="📍" label="Route & stop explorer" />
            <Feature icon="📅" label="GTFS schedules" />
            <Feature icon="🚌" label="Live vehicle tracking" />
            <Feature icon="⏱️" label="ETA predictions" />
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 px-6 py-3">
        <p className="text-center text-gray-600 text-xs">
          WaitWatch v0.1.0 — Stage 0: Project Foundation
        </p>
      </footer>
    </div>
  );
}

function Feature({ icon, label }: { icon: string; label: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-md px-3 py-2 flex items-center gap-2">
      <span>{icon}</span>
      <span className="text-gray-300">{label}</span>
    </div>
  );
}
