import React from "react";
import { Link } from "react-router-dom";

export default function Landing() {
  return (
    <div className="min-h-screen bg-slate-900 text-white flex flex-col items-center justify-center p-6">
      <div className="max-w-md text-center space-y-6">
        <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">
          Sunrise Multispeciality Hospital
        </h1>
        <p className="text-slate-400 text-lg">
          AI Hospital Appointment Orchestrator
        </p>
        <div className="flex gap-4 justify-center">
          <Link
            to="/login"
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg font-medium transition-colors"
          >
            Log In
          </Link>
          <Link
            to="/register"
            className="px-6 py-2 border border-slate-700 hover:bg-slate-800 rounded-lg font-medium transition-colors"
          >
            Register
          </Link>
        </div>
      </div>
    </div>
  );
}
