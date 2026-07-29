import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import API from "../services/api";

export default function PatientDashboard() {
  const [appointments, setAppointments] = useState([]);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [selectedApptId, setSelectedApptId] = useState(null);

  // Search, filter, and sort states
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("newest"); // newest, oldest
  const [showRightPanel, setShowRightPanel] = useState(true);

  const [patientInfo, setPatientInfo] = useState({
    name: "",
    age: "",
    gender: "",
    phone: "",
  });
  const [bookingStatus, setBookingStatus] = useState("awaiting_info");
  const [availableSlots, setAvailableSlots] = useState([]);
  const [triageInfo, setTriageInfo] = useState({
    department: "",
    priority: "",
    selectedDoctor: null,
  });

  const navigate = useNavigate();
  const chatEndRef = useRef(null);
  const textareaRef = useRef(null);
  const recognitionRef = useRef(null);
  const [isListening, setIsListening] = useState(false);
  const [usedVoiceForLastInput, setUsedVoiceForLastInput] = useState(false);
  const user = JSON.parse(localStorage.getItem("user") || "{}");

  useEffect(() => {
    // Scroll to bottom of chat when new messages arrive
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 128)}px`;
    }
  }, [inputValue]);

  // Speech Recognition (Speech-to-Text) Initialization
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const rec = new SpeechRecognition();
      rec.continuous = false;
      rec.interimResults = false;
      rec.lang = "en-US";
      
      rec.onstart = () => setIsListening(true);
      rec.onend = () => setIsListening(false);
      rec.onerror = (e) => {
        console.error("SpeechRecognition error:", e);
        setIsListening(false);
      };
      rec.onresult = (event) => {
        const text = event.results[0][0].transcript;
        setInputValue((prev) => (prev ? prev + " " + text : text));
        setUsedVoiceForLastInput(true);
      };
      recognitionRef.current = rec;
    }
  }, []);

  const toggleListening = () => {
    if (!recognitionRef.current) {
      alert("Speech recognition is not supported in this browser. Please try using Google Chrome or Apple Safari.");
      return;
    }
    if (isListening) {
      recognitionRef.current.stop();
    } else {
      recognitionRef.current.start();
    }
  };

  // Speech Synthesis (Text-to-Speech) Helper
  const speakText = (text) => {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    
    // Clean text by stripping markdown symbols
    const cleanText = text
      .replace(/\*\*?/g, "")
      .replace(/\[.*?\]/g, "")
      .replace(/Slot \d+:/gi, "");
      
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = "en-US";
    window.speechSynthesis.speak(utterance);
  };

  // Speak new assistant messages, skipping slot selection options, ONLY IF last user message was voice input
  useEffect(() => {
    if (messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.role === "assistant" && !loading) {
        const isSlotPresentation = 
          lastMsg.content.includes("Option 1") || 
          lastMsg.content.includes("Option 2") || 
          bookingStatus === "awaiting_slot_selection";
          
        if (!isSlotPresentation && usedVoiceForLastInput) {
          speakText(lastMsg.content);
        }
        // Always reset flag to prevent repeating voice readback on text typing
        setUsedVoiceForLastInput(false);
      }
    }
  }, [messages, bookingStatus, loading]);

  // Cancel speaking when exiting an active thread
  useEffect(() => {
    if (!selectedApptId && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
  }, [selectedApptId]);

  // Initial load
  useEffect(() => {
    // Seed initial patient info from database if available
    setPatientInfo({
      name: user.name || "",
      age: user.age || "",
      gender: user.gender || "",
      phone: user.phone || "",
    });
    fetchAppointments();
  }, []);

  const fetchAppointments = async () => {
    try {
      const response = await API.get("/api/appointments");
      setAppointments(response.data);
    } catch (err) {
      console.error("Failed to fetch appointments:", err);
    }
  };

  const handleCancelAppointment = async (apptId) => {
    if (!window.confirm("Are you sure you want to cancel this appointment?")) return;
    try {
      await API.post(`/api/appointments/${apptId}/cancel`);
      fetchAppointments();
      // Reload current chat details to reflect cancelled status
      const updatedAppt = appointments.find(a => a.id === apptId);
      if (updatedAppt) {
        handleSelectAppointment({ ...updatedAppt, status: "CANCELLED" });
      }
    } catch (err) {
      alert("Failed to cancel appointment. Please try again.");
    }
  };

  const handleStartNewConsultation = async () => {
    setLoading(true);
    try {
      const response = await API.post("/api/chat/new");
      const { session_id } = response.data;
      
      setSessionId(session_id);
      setSelectedApptId(`conv_${session_id}`);
      
      // Reset chatbot states for new session
      setBookingStatus("awaiting_info");
      setAvailableSlots([]);
      setTriageInfo({
        department: "",
        priority: "",
        selectedDoctor: null,
      });
      
      const welcomeMsg = {
        role: "assistant",
        content: `Hello ${user.name || "there"}! Welcome to Sunrise Multispeciality Hospital. I am your AI receptionist. Please tell me what symptoms or health concerns you are experiencing today so I can guide you to the right specialist.`,
      };
      setMessages([welcomeMsg]);
      
      await fetchAppointments();
    } catch (err) {
      console.error("Failed to start new consultation:", err);
      alert("Unable to start a new consultation. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleSelectAppointment = async (appt) => {
    setSelectedApptId(appt.id);
    await handleLoadChatSession(appt.conversation_id);
  };

  const handleLoadChatSession = async (sessionUuid) => {
    if (!sessionUuid) return;
    setLoading(true);
    try {
      const response = await API.get(`/api/chat/${sessionUuid}`);
      setSessionId(sessionUuid);
      setMessages(response.data.messages || []);
      if (response.data.patient_info) {
        setPatientInfo(response.data.patient_info);
      }
      if (response.data.booking_status) {
        setBookingStatus(response.data.booking_status);
      }
      if (response.data.available_slots) {
        setAvailableSlots(response.data.available_slots);
      } else {
        setAvailableSlots([]);
      }
      if (response.data.department) {
        setTriageInfo({
          department: response.data.department,
          priority: response.data.priority,
          selectedDoctor: response.data.selected_doctor,
        });
      } else {
        setTriageInfo({
          department: "",
          priority: "",
          selectedDoctor: null,
        });
      }
    } catch (err) {
      console.error("Failed to load chat history:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    if (!inputValue.trim() || loading || !sessionId) return;

    const userMessage = inputValue.trim();
    setInputValue("");
    setLoading(true);

    // Append user message locally
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);

    try {
      const response = await API.post("/api/chat", {
        session_id: sessionId,
        message: userMessage,
      });

      // Update message thread and extracted state from response
      setMessages(response.data.messages);
      if (response.data.session_id && response.data.session_id !== sessionId) {
        setSessionId(response.data.session_id);
      }
      if (response.data.patient_info) {
        setPatientInfo(response.data.patient_info);
      }
      if (response.data.booking_status) {
        setBookingStatus(response.data.booking_status);
      }
      if (response.data.available_slots) {
        setAvailableSlots(response.data.available_slots);
      } else {
        setAvailableSlots([]);
      }
      if (response.data.department) {
        setTriageInfo({
          department: response.data.department,
          priority: response.data.priority,
          selectedDoctor: response.data.selected_doctor,
        });
      }
      
      // Refresh list to pull updated symptoms or booking states
      fetchAppointments();
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, I encountered an issue connecting to the AI agent. Please try again shortly.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectSlotClick = async (optionNum) => {
    if (loading || !sessionId) return;
    setLoading(true);

    setMessages((prev) => [...prev, { role: "user", content: `Option ${optionNum}` }]);

    try {
      const response = await API.post("/api/chat", {
        session_id: sessionId,
        message: String(optionNum),
      });

      setMessages(response.data.messages);
      if (response.data.patient_info) {
        setPatientInfo(response.data.patient_info);
      }
      if (response.data.booking_status) {
        setBookingStatus(response.data.booking_status);
      }
      if (response.data.available_slots) {
        setAvailableSlots(response.data.available_slots);
      } else {
        setAvailableSlots([]);
      }
      if (response.data.department) {
        setTriageInfo({
          department: response.data.department,
          priority: response.data.priority,
          selectedDoctor: response.data.selected_doctor,
        });
      }
      fetchAppointments();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    navigate("/login");
  };

  // Helper: parse symptoms list for cards
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

  // Filter and sort consultations
  const filteredConsultations = appointments.filter((appt) => {
    const matchesSearch =
      appt.doctor_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      appt.specialization.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (appt.symptom_summary && appt.symptom_summary.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesStatus =
      statusFilter === "all" || appt.status.toLowerCase() === statusFilter;

    return matchesSearch && matchesStatus;
  });

  const sortedConsultations = [...filteredConsultations].sort((a, b) => {
    const dateA = new Date(a.created_at);
    const dateB = new Date(b.created_at);
    return sortBy === "newest" ? dateB - dateA : dateA - dateB;
  });

  const activeAppt = appointments.find(a => a.id === selectedApptId) || 
    (selectedApptId && selectedApptId.startsWith("conv_") ? {
      id: selectedApptId,
      doctor_name: "AI Triage Assistant",
      specialization: "Hospital Reception",
      status: "PENDING",
      date: "N/A",
      start_time: "N/A"
    } : null);

  const isReadOnly = activeAppt && ["COMPLETED", "CANCELLED", "MISSED"].includes(activeAppt.status);

  return (
    <div className="h-screen overflow-hidden bg-slate-950 text-white flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Top Header Bar */}
      <header className="bg-slate-900 border-b border-slate-800 px-6 py-4 flex justify-between items-center z-10 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-indigo-600 rounded-xl flex items-center justify-center font-bold text-lg shadow-lg shadow-indigo-500/20">
            🏥
          </div>
          <div>
            <h1 className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-indigo-400 via-indigo-200 to-white bg-clip-text text-transparent">
              Sunrise Multispeciality Hospital
            </h1>
            <p className="text-xs text-slate-500">Patient Care Hub</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right hidden sm:block">
            <p className="text-sm font-semibold text-slate-200">{user.name || "Patient"}</p>
            <p className="text-xs text-indigo-400 capitalize font-medium">{user.role || "User"}</p>
          </div>
          <button
            onClick={handleLogout}
            className="px-4 py-2 border border-slate-800 hover:bg-slate-800 text-slate-300 hover:text-white rounded-xl text-sm transition-colors cursor-pointer active:scale-95"
          >
            Log Out
          </button>
        </div>
      </header>

      {/* Main Layout Area */}
      <div className="flex-1 flex overflow-hidden">
        {selectedApptId === null ? (
          /* ========================================================================= */
          /* 1. APPOINTMENT DASHBOARD VIEW (LANDING PAGE)                             */
          /* ========================================================================= */
          <main className="flex-1 overflow-y-auto px-6 py-8 max-w-7xl mx-auto w-full space-y-8">
            
            {/* Banner block */}
            <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-slate-900 via-slate-900 to-indigo-950 border border-slate-850 p-8 shadow-2xl flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
              <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-500/5 rounded-full blur-3xl -z-10" />
              <div className="space-y-2">
                <span className="px-3 py-1 text-[10px] font-bold tracking-wider uppercase bg-indigo-500/20 text-indigo-300 rounded-full border border-indigo-500/30">
                  Patient Services Portal
                </span>
                <h2 className="text-3xl font-extrabold tracking-tight text-white">
                  Welcome, {user.name ? user.name.split(" ")[0] : "Patient"}
                </h2>
                <p className="text-slate-400 max-w-lg text-sm leading-relaxed">
                  Start a new online consultation or select an ongoing conversation below to reschedule, cancel, or review doctor summaries.
                </p>
              </div>
              <button
                onClick={handleStartNewConsultation}
                className="px-6 py-3.5 bg-indigo-650 hover:bg-indigo-650/90 text-white font-bold rounded-2xl transition duration-200 shadow-lg shadow-indigo-600/20 active:scale-95 cursor-pointer flex items-center gap-2 group shrink-0"
              >
                <span className="text-lg group-hover:rotate-90 transition duration-200">➕</span>
                Start New Consultation
              </button>
            </div>

            {/* Filter, Search & Sort Control Panel */}
            <div className="flex flex-col lg:flex-row gap-4 items-center justify-between bg-slate-900/40 p-4 rounded-2xl border border-slate-850">
              {/* Search Box */}
              <div className="relative w-full lg:w-80">
                <input
                  type="text"
                  placeholder="Search doctor or symptoms..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-850 rounded-xl px-4 py-2.5 pl-10 text-sm focus:outline-none focus:border-indigo-500 transition duration-200 text-slate-100 placeholder:text-slate-600"
                />
                <span className="absolute left-3.5 top-3 text-slate-600 text-sm">🔍</span>
              </div>

              {/* Filtering tabs */}
              <div className="flex flex-wrap bg-slate-950 p-1 rounded-xl border border-slate-850 w-full lg:w-auto gap-1">
                {["all", "pending", "upcoming", "completed", "missed", "cancelled"].map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setStatusFilter(tab)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all duration-200 cursor-pointer ${
                      statusFilter === tab
                        ? "bg-indigo-650 text-white shadow-md shadow-indigo-600/10"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {/* Sorting dropdown */}
              <div className="flex items-center gap-2 shrink-0 w-full lg:w-auto justify-end">
                <span className="text-xs text-slate-500 font-semibold uppercase">Sort:</span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="bg-slate-950 border border-slate-850 rounded-xl px-3 py-2 text-xs font-semibold focus:outline-none focus:border-indigo-500 cursor-pointer text-slate-300"
                >
                  <option value="newest">Newest Activity</option>
                  <option value="oldest">Oldest Activity</option>
                </select>
              </div>
            </div>

            {/* List Grid of Cards */}
            {sortedConsultations.length === 0 ? (
              <div className="border border-dashed border-slate-850 rounded-3xl py-24 text-center space-y-4">
                <div className="text-5xl text-slate-600">📁</div>
                <div className="space-y-1">
                  <h4 className="text-lg font-bold text-slate-350">No consultations found</h4>
                  <p className="text-xs text-slate-500 max-w-sm mx-auto">
                    {searchQuery || statusFilter !== "all"
                      ? "Try adjusting your filters or search keywords."
                      : "Start your first medical consultation by clicking the New Consultation button above."}
                  </p>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {sortedConsultations.map((appt) => {
                  const symptoms = getSymptomsList(appt.symptom_summary || appt.symptoms);
                  return (
                    <div
                      key={appt.id}
                      onClick={() => handleSelectAppointment(appt)}
                      className="bg-slate-900/40 border border-slate-850 rounded-2xl flex flex-col justify-between overflow-hidden hover:border-slate-700 hover:shadow-xl hover:shadow-indigo-950/20 hover:-translate-y-0.5 cursor-pointer transition duration-300 group"
                    >
                      <div className="p-6 space-y-4">
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <h4 className="font-extrabold text-slate-200 group-hover:text-indigo-400 transition duration-200">
                              {appt.doctor_name}
                            </h4>
                            <p className="text-xs text-slate-500 mt-0.5">
                              {appt.specialization} • Sunrise Hospital
                            </p>
                          </div>
                          <span
                            className={`px-2.5 py-0.5 text-[9px] font-extrabold uppercase tracking-wider rounded-full border shrink-0 ${
                              appt.status === "COMPLETED"
                                ? "bg-emerald-950/80 text-emerald-450 border-emerald-800"
                                : appt.status === "CANCELLED"
                                ? "bg-slate-900 text-slate-500 border-slate-800"
                                : appt.status === "MISSED"
                                ? "bg-rose-950/80 text-rose-450 border-rose-800"
                                : appt.status === "PENDING"
                                ? "bg-indigo-950/80 text-indigo-400 border-indigo-800 animate-pulse"
                                : "bg-blue-950/80 text-blue-400 border-blue-800"
                            }`}
                          >
                            {appt.status}
                          </span>
                        </div>

                        {/* Date Time info if booked */}
                        {appt.is_booked ? (
                          <div className="bg-slate-950/40 border border-slate-900 rounded-xl p-3 text-xs text-slate-400 space-y-1.5">
                            <div className="flex justify-between">
                              <span className="text-slate-600">Date:</span>
                              <span className="font-semibold text-slate-350">{appt.date}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-600">Time:</span>
                              <span className="font-semibold text-slate-350 font-mono">{appt.start_time}</span>
                            </div>
                          </div>
                        ) : (
                          <div className="bg-indigo-950/20 border border-indigo-900/30 rounded-xl p-3 text-xs text-indigo-400">
                            💬 Triage ongoing. Click to complete booking details.
                          </div>
                        )}

                        {/* Symptoms summary */}
                        {symptoms.length > 0 && (
                          <div className="space-y-1.5">
                            <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest block">Symptoms</span>
                            <div className="flex flex-wrap gap-1">
                              {symptoms.slice(0, 3).map((s, idx) => (
                                <span key={idx} className="px-2 py-0.5 text-[9px] font-medium bg-slate-950 text-slate-300 rounded border border-slate-850 capitalize">
                                  {s}
                                </span>
                              ))}
                              {symptoms.length > 3 && (
                                <span className="px-2 py-0.5 text-[9px] font-medium bg-slate-950 text-slate-500 rounded border border-slate-850">
                                  +{symptoms.length - 3} more
                                </span>
                              )}
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Card Footer: Activity status */}
                      <div className="bg-slate-950 border-t border-slate-900/80 px-6 py-3 flex items-center justify-between text-[10px] text-slate-500">
                        <span>Updated: {new Date(appt.created_at).toLocaleDateString()}</span>
                        <span className="text-indigo-400 font-bold group-hover:translate-x-1 transition duration-200">Open Chat ➔</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </main>
        ) : (
          /* ========================================================================= */
          /* 2. CHAT THREAD VIEW (WHATSAPP / CHATGPT SPLIT VIEW)                      */
          /* ========================================================================= */
          <main className="flex-1 flex overflow-hidden bg-slate-950">
            
            {/* Split Pane Left Column: Consultation Sidebar */}
            <aside className="w-80 border-r border-slate-900 bg-slate-900/30 hidden lg:flex flex-col">
              <div className="p-4 border-b border-slate-900 flex flex-col gap-3">
                <button
                  onClick={() => setSelectedApptId(null)}
                  className="px-4 py-2 border border-slate-800 hover:bg-slate-800 text-slate-300 hover:text-white rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-2"
                >
                  <span>🎛️</span> Back to Dashboard
                </button>
                <div className="relative">
                  <input
                    type="text"
                    placeholder="Search chats..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-850 rounded-xl px-3 py-1.5 pl-8 text-xs focus:outline-none focus:border-indigo-500 text-slate-200"
                  />
                  <span className="absolute left-2.5 top-2 text-slate-650 text-xs">🔍</span>
                </div>
              </div>

              {/* Vertical Sidebar List */}
              <div className="flex-1 overflow-y-auto p-2 space-y-1">
                {sortedConsultations.map((c) => (
                  <div
                    key={c.id}
                    onClick={() => handleSelectAppointment(c)}
                    className={`p-3 rounded-xl cursor-pointer transition-all duration-200 flex flex-col gap-1.5 ${
                      c.id === selectedApptId
                        ? "bg-indigo-650/20 border border-indigo-550/40"
                        : "hover:bg-slate-900/60 border border-transparent"
                    }`}
                  >
                    <div className="flex justify-between items-start gap-1">
                      <span className="font-bold text-xs text-slate-200 truncate">{c.doctor_name}</span>
                      <span className={`px-1.5 py-0.5 text-[8px] font-black uppercase rounded border shrink-0 ${
                        c.status === "COMPLETED"
                          ? "bg-emerald-950/85 text-emerald-450 border-emerald-900"
                          : c.status === "CANCELLED"
                          ? "bg-slate-900 text-slate-400 border-slate-800"
                          : c.status === "MISSED"
                          ? "bg-rose-950/85 text-rose-405 border-rose-900"
                          : c.status === "PENDING"
                          ? "bg-indigo-950/85 text-indigo-400 border-indigo-900 animate-pulse"
                          : "bg-blue-950/85 text-blue-400 border-blue-905"
                      }`}>
                        {c.status}
                      </span>
                    </div>
                    <div className="flex justify-between text-[9px] text-slate-500">
                      <span>{c.specialization}</span>
                      <span>{c.date !== "N/A" ? c.date : "Triage"}</span>
                    </div>
                  </div>
                ))}
              </div>
            </aside>

            {/* Split Pane Center Column: Messaging Window */}
            <section className="flex-1 flex flex-col relative bg-slate-950 overflow-hidden">
              
              {/* Active Chat Header */}
              <header className="bg-slate-900/60 border-b border-slate-900 px-6 py-4 flex items-center justify-between z-10 backdrop-blur flex-shrink-0">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setSelectedApptId(null)}
                    className="lg:hidden p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs cursor-pointer mr-1"
                  >
                    ⬅
                  </button>
                  <div>
                    <h3 className="font-extrabold text-sm text-slate-200">
                      {activeAppt ? activeAppt.doctor_name : "Consultation"}
                    </h3>
                    <p className="text-[10px] text-slate-500">
                      {activeAppt ? activeAppt.specialization : ""} • Sunrise Specialist
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <span className={`px-2 py-0.5 text-[9px] font-black uppercase rounded-full border ${
                    activeAppt && activeAppt.status === "COMPLETED"
                      ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                      : activeAppt && activeAppt.status === "CANCELLED"
                      ? "bg-slate-900 text-slate-500 border-slate-800"
                      : activeAppt && activeAppt.status === "MISSED"
                      ? "bg-rose-950 text-rose-455 border-rose-900"
                      : activeAppt && activeAppt.status === "PENDING"
                      ? "bg-indigo-950 text-indigo-400 border-indigo-800"
                      : "bg-blue-950 text-blue-400 border-blue-800"
                  }`}>
                    {activeAppt ? activeAppt.status : ""}
                  </span>
                  
                  {activeAppt && activeAppt.date !== "N/A" && (
                    <span className="text-[11px] font-mono bg-slate-900 border border-slate-850 px-2 py-1 rounded-lg text-slate-400">
                      {activeAppt.date} at {activeAppt.start_time}
                    </span>
                  )}

                  <button
                    onClick={() => setShowRightPanel(!showRightPanel)}
                    className="hidden md:block p-1.5 rounded-lg border border-slate-800 hover:bg-slate-900 text-xs cursor-pointer"
                    title="Toggle Info Panel"
                  >
                    ℹ️
                  </button>
                </div>
              </header>

              {/* Message Thread */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {messages.map((msg, index) => (
                  <div
                    key={index}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`whitespace-pre-line max-w-lg rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-md ${
                        msg.role === "user"
                          ? "bg-indigo-600 text-white rounded-tr-none"
                          : "bg-slate-900 text-slate-200 rounded-tl-none border border-slate-850"
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>
                ))}

                {/* Available Slot choice picker */}
                {!isReadOnly && bookingStatus === "awaiting_slot_selection" && availableSlots.length > 0 && (
                  <div className="flex flex-col gap-3 max-w-lg p-4 bg-slate-900/60 border border-slate-850 rounded-2xl my-2">
                    <p className="text-xs font-semibold text-slate-400">📅 Select an available slot to book:</p>
                    <div className="flex flex-col gap-2">
                      {availableSlots.map((slot, idx) => (
                        <button
                          key={slot.id}
                          type="button"
                          disabled={loading}
                          onClick={() => handleSelectSlotClick(idx + 1)}
                          className="w-full text-left px-4 py-3 bg-slate-950 hover:bg-indigo-650 border border-slate-800 hover:border-indigo-500 rounded-xl text-xs font-bold text-slate-300 hover:text-white transition-all cursor-pointer"
                        >
                          Option {idx + 1}: {slot.day}, {slot.date} at {slot.start_time}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {loading && (
                  <div className="flex justify-start">
                    <div className="bg-slate-900 text-slate-400 rounded-2xl rounded-tl-none px-4 py-3 border border-slate-850 flex items-center gap-2 text-sm">
                      <div className="flex gap-1">
                        <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce"></span>
                        <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce delay-150"></span>
                        <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce delay-300"></span>
                      </div>
                      Receptionist is typing...
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* Quick Actions Panel & Warnings based on status */}
              {activeAppt && (
                <div className="px-6 py-3 border-t border-slate-900 bg-slate-900/20">
                  {/* Missed Actions */}
                  {activeAppt.status === "MISSED" && (
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-rose-500/5 border border-rose-950/40 rounded-xl p-3 text-xs">
                      <div>
                        <p className="text-rose-400 font-bold">⚠️ Missed Appointment</p>
                        <p className="text-slate-400 text-[11px] mt-0.5">You did not attend this appointment. Would you like to schedule a new one?</p>
                      </div>
                      <button
                        onClick={handleStartNewConsultation}
                        className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-xl font-bold transition cursor-pointer active:scale-95 text-[11px] shrink-0"
                      >
                        Book New Appointment
                      </button>
                    </div>
                  )}

                  {/* Cancelled Actions */}
                  {activeAppt.status === "CANCELLED" && (
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-950 border border-slate-850 rounded-xl p-3 text-xs">
                      <div>
                        <p className="text-slate-400 font-bold">❌ Appointment Cancelled</p>
                        <p className="text-slate-500 text-[11px] mt-0.5">This chat is read-only. Would you like to start a completely new consultation?</p>
                      </div>
                      <button
                        onClick={handleStartNewConsultation}
                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-bold transition cursor-pointer active:scale-95 text-[11px] shrink-0"
                      >
                        Schedule New Appointment
                      </button>
                    </div>
                  )}

                  {/* Completed Actions */}
                  {activeAppt.status === "COMPLETED" && (
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-emerald-500/5 border border-emerald-950/40 rounded-xl p-3 text-xs">
                      <div className="flex-1">
                        <p className="text-emerald-450 font-bold">✅ Consultation Completed</p>
                        {activeAppt.doctor_notes && (
                          <div className="mt-1 bg-slate-950 p-2 border border-emerald-950/40 rounded-lg text-slate-300 font-medium">
                            <span className="text-[10px] text-emerald-450 font-bold block">Doctor's Recovery Notes:</span>
                            "{activeAppt.doctor_notes}"
                          </div>
                        )}
                      </div>
                      <button
                        onClick={handleStartNewConsultation}
                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-bold transition cursor-pointer active:scale-95 text-[11px] shrink-0 self-end sm:self-center"
                      >
                        Schedule New Consultation
                      </button>
                    </div>
                  )}

                  {/* Upcoming / Active Actions */}
                  {["UPCOMING", "SCHEDULED", "RESCHEDULED"].includes(activeAppt.status) && (
                    <div className="flex items-center justify-between gap-3 bg-slate-950 border border-slate-900 rounded-xl p-3 text-xs">
                      <p className="text-slate-400 font-medium">Need to reschedule or cancel this visit?</p>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleCancelAppointment(activeAppt.id)}
                          className="px-3.5 py-2 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-rose-455 rounded-lg transition font-bold cursor-pointer text-[10px]"
                        >
                          Cancel Appointment
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Message Input Panel */}
              <div className="p-4 bg-slate-900/40 border-t border-slate-900 flex-shrink-0">
                <form onSubmit={handleSendMessage} className="max-w-4xl mx-auto flex items-end gap-3">
                  <textarea
                    ref={textareaRef}
                    value={inputValue}
                    onChange={(e) => {
                      setInputValue(e.target.value);
                      setUsedVoiceForLastInput(false);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleSendMessage();
                      }
                    }}
                    disabled={loading || isReadOnly}
                    rows={1}
                    className="flex-1 bg-slate-950/80 border border-slate-850 rounded-xl px-4 py-3 text-white placeholder-slate-650 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all text-sm disabled:opacity-40 resize-none max-h-32 overflow-y-auto"
                    placeholder={isReadOnly ? "This conversation is read-only. Schedule a new consultation below." : "Type your message..."}
                  />
                  <button
                    type="button"
                    disabled={loading || isReadOnly}
                    onClick={toggleListening}
                    className={`p-3 rounded-xl border transition-all cursor-pointer h-[46px] w-[46px] flex items-center justify-center shrink-0 text-sm ${
                      isListening
                        ? "bg-rose-600 hover:bg-rose-500 border-rose-500 text-white animate-pulse"
                        : "bg-slate-950 hover:bg-slate-900 border-slate-850 text-slate-400 hover:text-white"
                    }`}
                    title={isListening ? "Listening..." : "Click to speak"}
                  >
                    🎤
                  </button>
                  <button
                    type="submit"
                    disabled={loading || isReadOnly || !inputValue.trim()}
                    className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-semibold rounded-xl transition-all shadow-md shadow-indigo-550/10 cursor-pointer flex items-center justify-center text-sm h-[46px] shrink-0"
                  >
                    Send
                  </button>
                </form>
              </div>
            </section>

            {/* Split Pane Right Column: Collapsible Triage Panel */}
            {showRightPanel && (
              <section className="w-80 bg-slate-905 border-l border-slate-900 p-6 flex flex-col gap-6 hidden md:flex overflow-y-auto">
                <div className="flex justify-between items-center border-b border-slate-900 pb-3">
                  <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Triage & Diagnostics</h3>
                  <button
                    onClick={() => setShowRightPanel(false)}
                    className="text-xs hover:text-white text-slate-500 cursor-pointer"
                  >
                    ✕
                  </button>
                </div>

                {/* Profile Stats */}
                <div className="space-y-3">
                  <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Extracted Profile</h4>
                  <div className="bg-slate-950 rounded-xl p-4 border border-slate-850 space-y-3.5 text-xs text-slate-350">
                    <div>
                      <p className="text-[10px] text-slate-550">Name</p>
                      <p className="font-semibold text-slate-200 mt-0.5">{patientInfo.name || <span className="text-slate-700 italic">None</span>}</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-slate-550">Age</p>
                      <p className="font-semibold text-slate-200 mt-0.5">{patientInfo.age !== undefined && patientInfo.age !== "" ? patientInfo.age : <span className="text-slate-700 italic">None</span>}</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-slate-550">Gender</p>
                      <p className="font-semibold text-slate-200 mt-0.5 capitalize">{patientInfo.gender || <span className="text-slate-700 italic">None</span>}</p>
                    </div>
                  </div>
                </div>

                {/* Triage Info */}
                {triageInfo.department && (
                  <div className="space-y-3">
                    <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Medical Triage</h4>
                    <div className="bg-slate-950 rounded-xl p-4 border border-slate-850 space-y-3.5 text-xs text-slate-350">
                      <div>
                        <p className="text-[10px] text-slate-550">Department</p>
                        <p className="font-semibold text-slate-200 mt-0.5">{triageInfo.department}</p>
                      </div>
                      <div>
                        <p className="text-[10px] text-slate-550">Priority Level</p>
                        <span
                          className={`inline-block px-2.5 py-0.5 rounded-full text-[10px] font-bold mt-1 capitalize border ${
                            triageInfo.priority === "EMERGENCY"
                              ? "bg-red-950/80 text-red-400 border-red-800 animate-pulse"
                              : triageInfo.priority === "HIGH"
                              ? "bg-orange-950/80 text-orange-400 border-orange-800"
                              : triageInfo.priority === "MEDIUM"
                              ? "bg-amber-950/80 text-amber-400 border-amber-800"
                              : "bg-blue-950/80 text-blue-400 border-blue-800"
                          }`}
                        >
                          {triageInfo.priority}
                        </span>
                      </div>
                      {triageInfo.selectedDoctor && (
                        <div>
                          <p className="text-[10px] text-slate-550">Recommended Doctor</p>
                          <p className="font-semibold text-slate-200 mt-0.5">{triageInfo.selectedDoctor.name}</p>
                          <p className="text-[10px] text-slate-500 font-medium">
                            {triageInfo.selectedDoctor.specialization} ({triageInfo.selectedDoctor.experience_years} Yrs Exp)
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </section>
            )}
          </main>
        )}
      </div>
    </div>
  );
}
