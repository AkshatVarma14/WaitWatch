import { ArrivalsBoard } from "../components/arrivalsBoard";
import { FeedSelector } from "../components/feedSelector";
import { MapDetailsPanel } from "../components/mapDetailsPanel";
import { MapView } from "../components/mapView";
import { RouteSelector } from "../components/routeSelector";
import { StopSearch } from "../components/stopSearch";

export function Dashboard() {
  return (
    <div className="min-h-screen bg-gray-950 text-white flex flex-col font-sans">
      {/* Top Application Header */}
      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-20 px-4 sm:px-6 py-3.5">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl" role="img" aria-label="Bus">
              🚌
            </span>
            <div>
              <h1 className="text-lg font-bold tracking-tight leading-none">
                WaitWatch
              </h1>
              <p className="text-[11px] text-gray-400 hidden sm:block mt-0.5">
                Real-Time Transit Tracking
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gray-900 border border-gray-800">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Stage 4: Map & Transit Explorer
            </span>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 space-y-6">
        <div>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Real-Time Transit Tracking
          </h2>
          <p className="text-sm text-gray-400 mt-1 max-w-3xl">
            Explore transit feeds, select routes to view true GTFS shape
            geometry and live vehicles on the map, and get real-time stop arrival
            predictions.
          </p>
        </div>

        {/* Feed & Route Controls */}
        <section
          className="grid grid-cols-1 md:grid-cols-2 gap-4"
          aria-label="Feed and route selection"
        >
          <FeedSelector />
          <RouteSelector />
        </section>

        {/* Map Visualization & Route Explorer */}
        <section
          className="grid grid-cols-1 lg:grid-cols-12 gap-6"
          aria-label="Route map visualization"
        >
          <div className="lg:col-span-8 space-y-4">
            <MapView />
          </div>
          <div className="lg:col-span-4 space-y-4">
            <MapDetailsPanel />
          </div>
        </section>

        {/* Stop Navigation & Live Arrivals */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Stop Search (5 cols on lg) */}
          <section
            className="lg:col-span-5 space-y-6"
            aria-label="Feed and stop navigation"
          >
            <StopSearch />
          </section>

          {/* Right Column: Arrivals Board (7 cols on lg) */}
          <section
            className="lg:col-span-7"
            aria-label="Stop arrivals display"
          >
            <ArrivalsBoard />
          </section>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 px-6 py-4 bg-gray-950 mt-auto">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-gray-500">
          <p>
            WaitWatch v0.4.2 — Interactive Map & Route Visualization
          </p>
          <p>
            GTFS Static Shapes & GTFS-Realtime Telemetry Integration
          </p>
        </div>
      </footer>
    </div>
  );
}
