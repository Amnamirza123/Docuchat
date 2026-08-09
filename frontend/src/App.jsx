import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { supabase } from "./lib/supabaseClient";

import Register from "./pages/Register";
import Login from "./pages/Login";
import Chat from "./pages/Chat";

function ProtectedRoute({ session, children }) {
  if (!session) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  const [session, setSession] = useState(undefined); // undefined = still loading

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
    });

    const { data: listener } = supabase.auth.onAuthStateChange(
      (_event, newSession) => {
        setSession(newSession);
      }
    );

    return () => listener.subscription.unsubscribe();
  }, []);

  if (session === undefined) {
    // Still checking for an existing session — avoid a flash of the login page
    return <div className="app-loading">Loading...</div>;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/register" element={<Register />} />
        <Route path="/login" element={<Login />} />
        <Route
          path="/chat"
          element={
            <ProtectedRoute session={session}>
              <Chat />
            </ProtectedRoute>
          }
        />
        <Route
          path="/"
          element={<Navigate to={session ? "/chat" : "/login"} replace />}
        />
      </Routes>
    </BrowserRouter>
  );
}