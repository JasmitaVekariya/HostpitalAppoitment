import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import API from "../services/api";

export default function DoctorDashboard() {
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all"); // all, upcoming, completed, missed, cancelled
  const [notesState, setNotesState] = useState({});

  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");

  useEffect(() => {
    fetchDoctorAppointments();
  }, []);

  const fetchDoctorAppointments = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await API.get("/api/doctor/appointments");
      setAppointments(response.data);
    } catch (err) {
      console.error("Failed to load doctor appointments:", err);
      setError("Unable to load appointments. Please check your connection.");
    } finally {
      setLoading(false);
    }
  };

  const handleCompleteAppointment = async (apptId) => {
    try {
      const note = notesState[apptId] || "";
      await API.post(`/api/appointments/${apptId}/complete`, { doctor_notes: note });
      // Reset the local notes state for this card
      setNotesState(prev => {
        const next = { ...prev };
        delete next[apptId];
        return next;
      });
      fetchDoctorAppointments();
    } catch (err) {
      console.error("Failed to complete appointment:", err);
      alert("Failed to complete appointment. Please try again.");
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    navigate("/login");
  };

  // Filter and search logic
  const filteredAppointments = appointments.filter((appt) => {
    const matchesSearch =
      appt.patient_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      appt.symptoms.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesStatus =
      statusFilter === "all" || appt.status.toLowerCase() === statusFilter;

    return matchesSearch && matchesStatus;
  });

  // Calculate quick metrics
  const totalBookings = appointments.length;
  const confirmedCount = appointments.filter((a) => a.status === "UPCOMING" || a.status === "SCHEDULED" || a.status === "RESCHEDULED").length;
  const completedCount = appointments.filter((a) => a.status === "COMPLETED").length;
  const missedCount = appointments.filter((a) => a.status === "MISSED").length;
  const cancelledCount = appointments.filter((a) => a.status === "CANCELLED").length;

  return (
    <div className="min-h-screen bg-slate-950 text-white font-sans selection:bg-indigo-500 selection:text-white">
      {/* Top Navigation Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur sticky top-0 z-50 px-6 py-4">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <span className="font-extrabold text-lg text-white">🏥</span>
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
                Sunrise Hospital
              </h1>
              <p className="text-xs font-semibold text-indigo-400 uppercase tracking-widest">
                Doctor Console
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-semibold text-slate-200">
                Dr. {user.name || "Specialist"}
              </p>
              <p className="text-xs text-slate-400">
                {user.email || "Medical Staff"}
              </p>
            </div>
            <button
              onClick={handleLogout}
              className="px-4 py-2 text-xs font-bold uppercase tracking-wider bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition duration-200 border border-slate-700 active:scale-95"
            >
              Log Out
            </button>
          </div>
        </div>
      </header>

      {/* Main Body */}
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        
        {/* Banner/Intro */}
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-slate-900 via-slate-900 to-indigo-950 border border-slate-800 p-8 shadow-2xl">
          <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-500/10 rounded-full blur-3xl -z-10" />
          <div className="space-y-2">
            <span className="px-3 py-1 text-[10px] font-bold tracking-wider uppercase bg-indigo-500/20 text-indigo-300 rounded-full border border-indigo-500/30">
              Personalized Dashboard
            </span>
            <h2 className="text-3xl font-extrabold tracking-tight md:text-4xl text-white">
              Welcome back, Dr. {user.name ? user.name.split(" ")[0] : "Specialist"}
            </h2>
            <p className="text-slate-400 max-w-xl text-sm leading-relaxed">
              Review and manage your patient check-in schedules, AI-extracted triage symptoms, and active calendar bookings.
            </p>
          </div>
        </div>

        {/* Metrics Row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Card 1: Total Appointments */}
          <div className="bg-slate-900/60 backdrop-blur border border-slate-800 p-6 rounded-2xl flex items-center justify-between shadow-lg hover:border-slate-700 transition duration-300">
            <div className="space-y-1">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Bookings</p>
              <h3 className="text-3xl font-black text-white">{totalBookings}</h3>
            </div>
            <div className="w-12 h-12 rounded-xl bg-slate-800 flex items-center justify-center text-xl">
              📅
            </div>
          </div>

          {/* Card 2: Confirmed Appointments */}
          <div className="bg-slate-900/60 backdrop-blur border border-slate-800 p-6 rounded-2xl flex items-center justify-between shadow-lg hover:border-slate-700 transition duration-300">
            <div className="space-y-1">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Confirmed Slots</p>
              <h3 className="text-3xl font-black text-emerald-400">{confirmedCount}</h3>
            </div>
            <div className="w-12 h-12 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center text-xl">
              ✅
            </div>
          </div>

          {/* Card 3: Cancelled Appointments */}
          <div className="bg-slate-900/60 backdrop-blur border border-slate-800 p-6 rounded-2xl flex items-center justify-between shadow-lg hover:border-slate-700 transition duration-300">
            <div className="space-y-1">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Released/Cancelled</p>
              <h3 className="text-3xl font-black text-rose-400">{cancelledCount}</h3>
            </div>
            <div className="w-12 h-12 rounded-xl bg-rose-500/10 text-rose-400 flex items-center justify-center text-xl">
              ❌
            </div>
          </div>
        </div>

        {/* Filter and Search Bar */}
        <div className="flex flex-col md:flex-row gap-4 items-center justify-between bg-slate-900/40 p-4 rounded-2xl border border-slate-800/80">
          {/* Search Box */}
          <div className="relative w-full md:w-80">
            <input
              type="text"
              placeholder="Search patient name or symptoms..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 pl-10 text-sm focus:outline-none focus:border-indigo-500 transition duration-200 text-slate-100 placeholder:text-slate-600"
            />
            <span className="absolute left-3.5 top-3.5 text-slate-600 text-sm">🔍</span>
          </div>

          {/* Status Tabs */}
          <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800 w-full md:w-auto">
            {["all", "pending", "upcoming", "completed", "missed", "cancelled"].map((tab) => (
              <button
                key={tab}
                onClick={() => setStatusFilter(tab)}
                className={`flex-1 md:flex-initial px-4 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all duration-200 ${
                  statusFilter === tab
                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/10"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        {/* List Section */}
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <div className="w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm font-semibold text-slate-400">Loading patient schedule...</p>
          </div>
        ) : error ? (
          <div className="bg-rose-500/10 border border-rose-500/20 text-rose-300 rounded-2xl p-6 text-center max-w-md mx-auto space-y-4">
            <p className="text-sm font-medium">{error}</p>
            <button
              onClick={fetchDoctorAppointments}
              className="px-4 py-2 text-xs font-bold uppercase bg-rose-500 hover:bg-rose-600 text-white rounded-xl transition duration-200"
            >
              Retry Load
            </button>
          </div>
        ) : filteredAppointments.length === 0 ? (
          <div className="border border-dashed border-slate-850 rounded-2xl py-20 text-center space-y-4">
            <div className="text-5xl text-slate-600">📁</div>
            <div className="space-y-1">
              <h4 className="text-lg font-bold text-slate-300">No Appointments Found</h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                {searchQuery || statusFilter !== "all"
                  ? "Try adjusting your search criteria or filters."
                  : "You currently have no patient appointments booked."}
              </p>
            </div>
          </div>
        ) : (
          /* Cards Grid */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredAppointments.map((appt) => (
              <div
                key={appt.id}
                className="bg-slate-900/40 border border-slate-800 rounded-2xl flex flex-col justify-between overflow-hidden hover:border-slate-700 hover:shadow-xl hover:shadow-indigo-950/20 transition duration-300"
              >
                {/* Header: Patient Profile Info */}
                <div className="p-6 space-y-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center font-extrabold text-indigo-400">
                        {appt.patient_name.charAt(0)}
                      </div>
                      <div>
                        <h4 className="font-extrabold text-slate-200 leading-tight">
                          {appt.patient_name}
                        </h4>
                        <p className="text-xs text-slate-500">
                          {appt.patient_age} yrs • {appt.patient_gender}
                        </p>
                      </div>
                    </div>
                    {/* Status Badge */}
                    <span
                      className={`px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider rounded-full ${
                        appt.status === "COMPLETED"
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          : appt.status === "CANCELLED"
                          ? "bg-rose-500/10 text-rose-450 border border-rose-500/20"
                          : appt.status === "MISSED"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-550/20"
                          : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                      }`}
                    >
                      {appt.status}
                    </span>
                  </div>

                  {/* Patient Contact details */}
                  <div className="bg-slate-950/40 rounded-xl p-3 border border-slate-900/60 text-xs space-y-1.5 text-slate-400">
                    <div className="flex justify-between">
                      <span className="text-slate-600">Phone:</span>
                      <span className="font-semibold text-slate-300">{appt.patient_phone}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-600">Email:</span>
                      <span className="font-semibold text-slate-300 truncate max-w-[160px]" title={appt.patient_email}>
                        {appt.patient_email}
                      </span>
                    </div>
                  </div>

                  {/* AI Triage / Reason for Visit */}
                  <div className="space-y-1.5">
                    <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">
                      AI Triage Reason
                    </span>
                    <p className="text-xs bg-slate-950 border border-slate-800 p-3.5 rounded-xl text-slate-300 leading-relaxed italic">
                      "{appt.symptoms}"
                    </p>
                    {/* Symptoms Chips */}
                    {(() => {
                      const getSymptomsList = (symptomsStr) => {
                        if (!symptomsStr) return [];
                        if (symptomsStr.startsWith("[") && symptomsStr.endsWith("]")) {
                          try {
                            const cleaned = symptomsStr.replace(/'/g, '"');
                            return JSON.parse(cleaned);
                          } catch (e) {
                            return symptomsStr.slice(1, -1).split(",").map(s => s.trim().replace(/['"]/g, ""));
                          }
                        }
                        return symptomsStr.split(",").map(s => s.trim());
                      };
                      const chips = getSymptomsList(appt.symptom_summary || appt.symptoms);
                      if (chips.length === 0) return null;
                      return (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {chips.map((chip, idx) => (
                            <span key={idx} className="px-2 py-0.5 text-[9px] font-semibold bg-indigo-500/10 text-indigo-300 rounded-md border border-indigo-500/20 capitalize">
                              {chip}
                            </span>
                          ))}
                        </div>
                      );
                    })()}
                  </div>

                  {/* Pending Approval Section */}
                  {appt.status === "PENDING" && (
                    <div className="space-y-2 pt-2 border-t border-slate-800/80">
                      <span className="text-[10px] font-bold text-amber-400 uppercase tracking-widest block">
                        Requires Approval
                      </span>
                      <p className="text-xs text-slate-300 leading-relaxed bg-amber-500/10 p-2.5 border border-amber-500/20 rounded-xl mb-2">
                        The AI triage requested a slot. Do you approve this appointment?
                      </p>
                      <div className="flex gap-2">
                        <button
                          onClick={async () => {
                            if (window.confirm("Approve this appointment?")) {
                              try {
                                await API.get(`/api/human-review/${appt.conversation_id}/APPROVE`);
                                fetchDoctorAppointments();
                              } catch (err) {
                                alert("Failed to approve appointment.");
                              }
                            }
                          }}
                          className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white text-xs font-bold rounded-xl transition duration-200"
                        >
                          Approve
                        </button>
                        <button
                          onClick={async () => {
                            if (window.confirm("Reject this appointment?")) {
                              try {
                                await API.get(`/api/human-review/${appt.conversation_id}/REJECT`);
                                fetchDoctorAppointments();
                              } catch (err) {
                                alert("Failed to reject appointment.");
                              }
                            }
                          }}
                          className="flex-1 py-2 bg-rose-600 hover:bg-rose-500 active:scale-95 text-white text-xs font-bold rounded-xl transition duration-200"
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Doctor Notes & Action Section */}
                  {["UPCOMING", "SCHEDULED", "RESCHEDULED"].includes(appt.status) && (
                    <div className="space-y-2 pt-2 border-t border-slate-800/80">
                      <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest block">
                        Record Doctor Notes
                      </span>
                      <textarea
                        placeholder="Add patient recovery notes, prescriptions, or follow-up instructions..."
                        value={notesState[appt.id] || ""}
                        onChange={(e) => setNotesState({ ...notesState, [appt.id]: e.target.value })}
                        className="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-xs text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500"
                        rows={2}
                      />
                      <button
                        onClick={() => handleCompleteAppointment(appt.id)}
                        className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white text-xs font-bold rounded-xl transition duration-200"
                      >
                        Mark as Completed
                      </button>
                    </div>
                  )}

                  {appt.status === "COMPLETED" && (
                    <div className="space-y-2 pt-2 border-t border-slate-800/80">
                      <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest block">
                        Completed Notes
                      </span>
                      <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/60 p-2.5 border border-emerald-950/60 rounded-xl">
                        {appt.doctor_notes || "No notes recorded."}
                      </p>
                      {appt.completed_at && (
                        <p className="text-[9px] text-slate-500">
                          Completed on: {new Date(appt.completed_at).toLocaleString()}
                        </p>
                      )}
                    </div>
                  )}

                  {appt.status === "MISSED" && (
                    <div className="pt-2 border-t border-slate-800/80 text-center text-xs text-rose-450 bg-rose-500/5 p-2.5 border border-rose-950/40 rounded-xl">
                      ⚠️ Patient missed this appointment.
                    </div>
                  )}

                  {appt.status === "CANCELLED" && (
                    <div className="pt-2 border-t border-slate-800/80 text-center text-xs text-slate-500 bg-slate-950/80 p-2.5 border border-slate-850 rounded-xl">
                      ❌ This appointment was cancelled.
                    </div>
                  )}
                </div>

                {/* Footer: Time and slot details */}
                <div className="bg-slate-950 border-t border-slate-900 px-6 py-4 flex items-center justify-between text-xs text-slate-400">
                  <div className="flex items-center gap-2">
                    <span>📅</span>
                    <span className="font-semibold text-slate-300">{appt.date}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span>⏰</span>
                    <span className="font-semibold text-slate-300">{appt.start_time}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
