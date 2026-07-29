import React from "react";
import { Navigate } from "react-router-dom";

export default function ProtectedRoute({ children, allowedRoles }) {
  const token = localStorage.getItem("token");
  const userJson = localStorage.getItem("user");
  
  if (!token || !userJson) {
    // Redirect to login if not authenticated
    return <Navigate to="/login" replace />;
  }

  try {
    const user = JSON.parse(userJson);
    
    // Check if the user's role is permitted
    if (allowedRoles && !allowedRoles.includes(user.role)) {
      // Redirect to home if they don't have access
      return <Navigate to="/" replace />;
    }
  } catch (e) {
    // Clear corrupted auth data
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    return <Navigate to="/login" replace />;
  }

  return children;
}
