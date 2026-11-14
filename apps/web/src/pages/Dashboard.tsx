import { useState } from "react";
import { ArrivalsBoard } from "../components/arrivalsBoard";
import { FeedSelector } from "../components/feedSelector";
import { MapDetailsPanel } from "../components/mapDetailsPanel";
import { MapView } from "../components/mapView";
import { RouteSelector } from "../components/routeSelector";
import { StopSearch } from "../components/stopSearch";
import { TripPlanner } from "../components/tripPlanner";
import { useFeedLiveUpdates } from "../lib/useFeedLiveUpdates";
import { useAppStore } from "../stores/appStore";

export function Dashboard() {
  const selectedFeedSlug = useAppStore((state) => state.selectedFeedSlug);
  const liveStatus = useAppStore((state) => state.liveStatus);
  const [activeTab, setActiveTab] = useState<"arrivals" | "planner">("arrivals");

  // Subscribe to feed-scoped WebSocket live transit updates
  useFeedLiveUpdates(selectedFeedSlug);

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
            {selectedFeedSlug && (
              <span
                role="status"
                aria-label={`Live status: ${liveStatus}`}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border ${
                  liveStatus === "connected"
                    ? "bg-emerald-950/70 text-emerald-300 border-emerald-800"
                    : liveStatus === "fallback"
                      ? "bg-blue-950/70 text-blue-300 border-blue-800"
                      : "bg-gray-900 text-gray-400 border-gray-800"
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    liveStatus === "connected"
                      ? "bg-emerald-400 animate-pulse"
                      : liveStatus === "fallback"
                        ? "bg-blue-400 animate-pulse"
                        : "bg-gray-500"
                  }`}
                />
                {liveStatus === "connected"
                  ? "Live (WS)"
                  : liveStatus === "fallback"
                    ? "Live (30s)"
                    : liveStatus === "paused"
                      ? "Paused"
                      : "Connecting..."}
              </span>
            )}
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
            Explore routes and live vehicles on the map, look up stop schedules, and view real-time arrival predictions.
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

        {/* Section Navigation Tabs */}
        <div
          role="tablist"
          aria-label="Transit modes"
          className="flex items-center gap-2 border-b border-gray-800 pb-2"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "arrivals"}
            onClick={() => setActiveTab("arrivals")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === "arrivals"
                ? "bg-blue-600 text-white shadow-sm"
                : "bg-gray-900 text-gray-400 hover:text-white hover:bg-gray-800"
            }`}
          >
            🚏 Stop Explorer & Arrivals
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "planner"}
            onClick={() => setActiveTab("planner")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === "planner"
                ? "bg-blue-600 text-white shadow-sm"
                : "bg-gray-900 text-gray-400 hover:text-white hover:bg-gray-800"
            }`}
          >
            🧭 Direct Trip Planner
          </button>
        </div>

        {/* Tab Content */}
        {activeTab === "arrivals" ? (
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
        ) : (
          <section aria-label="Direct trip planner section">
            <TripPlanner />
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 px-6 py-4 bg-gray-950 mt-auto">
        <div className="max-w-7xl mx-auto flex flex-col items-center gap-2 text-xs text-gray-500 text-center">
          <p>
            WaitWatch — Real-Time Transit Tracking
          </p>
          <p>
            Bus schedule data: {" "}
            <a
              href="https://delhi.transportstack.in/data-services"
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-gray-300"
            >
              Delhi Transport Stack (DTC / DoT)
            </a>
            {" · "}
            Live positions: {" "}
            <a
              href="https://otd.delhi.gov.in/"
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-gray-300"
            >
              Open Transit Data Delhi
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
